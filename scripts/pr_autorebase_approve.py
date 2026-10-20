#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变基后自动批准 `action_required` 的 CI runs（源 GitHub #2419）。

WHY
===
`pr-auto-rebase.yml` 用 `GITHUB_TOKEN` 推分支 ⇒ GitHub 的递归防护把该分支新产生的
workflow runs 标成 `action_required`：**没人点 Approve 就零 job、永远挂死**
（GitHub #2289 记的就是这件事）。

旧实现（内联在 workflow 里的 shell）在 push 之后紧接 3 轮 × `sleep 10` 去查
`status=action_required`，两个独立缺陷：

**(a) 它根本没被执行过。** `pull_request_target` 的 workflow **定义**取自默认分支 `main`，
而该逻辑（GitHub #2289）只合进了 `dev` ⇒ `main` 上那份脚本里没有这段循环。
实测（2026-10-19 run `39290214996`）：`main` 的 33 行脚本在日志里 33 行全中，
`dev` 的批准循环 10 行一行未现。详见 `docs/dev/github-action.md`。

**(b) 一旦真的跑起来，它会把「空」读成「无需批准」。** 窗口只有 30s，
且用 `status=action_required` 过滤 —— 过滤后为空时，「还没索引到」与「没有待批」
长得一模一样，作业绿、机制没干活（与 AGENTS.md「空 ≠ 没拿到」同族）。

所以本脚本既修 (b) 的判据，也让 (a) 可自证：脚本与 workflow 都显式取 `dev`
（`ref: dev` + `git show origin/dev:<脚本>`），并打印 `AUTOREBASE_APPROVE …`
一行汇总 —— 发版后看日志里有没有这行，就知道新逻辑有没有真的跑。`docs/dev/github-action.md`
里给了核实命令。

本脚本做三件旧实现做不到的事
============================
1. **先看全量 runs 再筛**（不带 `status=` 过滤）：能区分「一条 run 都没有（索引滞后 /
   该 head 没触发任何 workflow）」与「有 run 但不需要批准」。旧实现把两者读成同一句话，
   而这两者的处置完全相反。
2. **窗口按需延长 + 命中即收工**：默认最长 180s，一旦批准过、且下一轮没有新目标就提前返回
   （一次变基通常同时产生 3~4 个 run，一轮复检足够），不会把每个 PR 都拖满 3 分钟。
3. **失败态显式**：拿不到输入 `rc 2`、批准调用失败 `rc 3`、一条 run 都没看到就打
   `::warning::` 注解（GitHub 会把它显示在 run 页面上，不是埋在日志里）。

退出码
======
    0 = 无需批准 / 已全部批准（`seen=0` 时另行打 warning 注解，**不判红**：
        它可能是索引滞后、也可能是该 head 真的没有 workflow，这一层由人判断）
    2 = **拿不到输入**（每一轮查询都失败）⇒ 结论不可信，**不得**读成「无需批准」
    3 = 有该批准的 run，但批准调用失败 ⇒ 需人工点 Approve

用法
====
    python scripts/pr_autorebase_approve.py --repo imoyao/fundmate --sha <head-sha>
    python scripts/pr_autorebase_approve.py --repo ... --sha ... --dry-run   # 只报告不批准
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time


def _gh_api(path: str, method: str = 'GET') -> tuple[int, str]:
    """调 `gh api`，返回 `(rc, stdout)`。用 `gh` 而不是 urllib：workflow 里已有 GH_TOKEN。"""
    cmd = ['gh', 'api']
    if method != 'GET':
        cmd += ['-X', method]
    cmd.append(path)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, (r.stdout or '').strip()


def list_runs(repo: str, sha: str) -> tuple[bool, list[dict]]:
    """列出该 head_sha 上的全部 workflow runs。

    **刻意不带 `status=action_required`**：过滤后为空时，「没有待批」与「还没索引到」
    长得一模一样 —— 这正是 #2419 的病根。拿全量再在本地筛，两种情形才分得开。
    """
    code, out = _gh_api(f'repos/{repo}/actions/runs?head_sha={sha}&per_page=100')
    if code != 0:
        return False, []
    try:
        data = json.loads(out or '{}')
    except json.JSONDecodeError:
        return False, []
    runs = data.get('workflow_runs')
    return (True, runs) if isinstance(runs, list) else (False, [])


def approve_run(repo: str, run_id: int) -> bool:
    code, _ = _gh_api(f'repos/{repo}/actions/runs/{run_id}/approve', method='POST')
    return code == 0


def _needs_approval(run: dict) -> bool:
    """该 run 是否卡在「等待批准」。

    GitHub 对同一状态的两种写法都出现过：列表/详情里通常是
    `status=completed` + `conclusion=action_required`，但也有 `status=action_required`
    的形态（旧实现在 URL 上用 `status=action_required` 就能筛出来，就是这个原因）。
    两个字段任一命中即可，避免只认一种写法而漏批。
    """
    return 'action_required' in (run.get('status'), run.get('conclusion'))


def run(args: argparse.Namespace) -> int:
    deadline = time.monotonic() + max(0.0, args.max_wait)
    seen: dict[int, dict] = {}
    approved: list[int] = []
    failed: list[int] = []
    queries_ok = 0
    queries_fail = 0
    rounds = 0

    while True:
        rounds += 1
        ok, runs = list_runs(args.repo, args.sha)
        if ok:
            queries_ok += 1
            seen.update({int(r['id']): r for r in runs if isinstance(r, dict) and 'id' in r})
        else:
            queries_fail += 1
            print(f'⚠️ 第 {rounds} 轮查询 runs 失败（head={args.sha[:12]}）', file=sys.stderr)

        targets: list[int] = []
        if ok:
            for r in runs:
                if not isinstance(r, dict) or 'id' not in r:
                    continue
                rid = int(r['id'])
                if not _needs_approval(r) or rid in approved or rid in failed:
                    continue
                targets.append(rid)

        for rid in targets:
            if args.dry_run:
                print(f'· [dry-run] 该批准 run {rid}（变基后 action_required）')
                approved.append(rid)
                continue
            if approve_run(args.repo, rid):
                print(f'✅ 已批准 run {rid}（变基后 action_required）')
                approved.append(rid)
            else:
                print(f'⚠️ 批准 run {rid} 失败 —— 请到 Actions 页人工点 Approve，否则该 CI 挂死', file=sys.stderr)
                failed.append(rid)

        # 命中且本轮没有新目标 ⇒ 收工（一轮复检已覆盖「同一批 run 陆续出现」的常态）
        if approved and not targets:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.0, args.interval))

    print(
        f'AUTOREBASE_APPROVE seen={len(seen)} approved={len(approved)} failed={len(failed)} '
        f'queries={queries_ok}/{queries_ok + queries_fail} rounds={rounds}'
    )

    if queries_ok == 0:
        print(
            '❌ 拿不到输入：所有查询都失败 —— **本轮结论不可信**（不得读成「无需批准」，源 GitHub #2419）',
            file=sys.stderr,
        )
        return 2
    if failed:
        print(
            f'❌ 有 {len(failed)} 个 run 该批准但没批成：{failed} —— 请到 Actions 页人工点 Approve',
            file=sys.stderr,
        )
        return 3
    if not seen:
        print(
            '::warning::变基后一条 run 都没看到（head=' + args.sha[:12] + '）—— 可能是索引滞后，'
            '也可能是该 head 没触发任何 workflow。**不要**读成「无需批准」：请到 Actions 页确认。'
        )
        return 0
    if not approved:
        print(f'ℹ️ 新 head 上 {len(seen)} 条 run 都无需批准（没有 action_required）')
        return 0
    if args.dry_run:
        print(f'ℹ️ [dry-run] 该批准 {len(approved)} 个 run：{approved}（**未真批准**）')
        return 0
    print(f'✅ 已批准 {len(approved)} 个 run：{approved}')
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='批准变基后 action_required 的 CI runs（源 GitHub #2419）')
    p.add_argument(
        '--repo', default=os.environ.get('GITHUB_REPOSITORY', ''), help='owner/name（默认取 GITHUB_REPOSITORY）'
    )
    p.add_argument('--sha', required=True, help='变基后的 head sha')
    p.add_argument('--interval', type=float, default=15.0, help='轮询间隔秒（默认 15）')
    p.add_argument('--max-wait', type=float, default=180.0, help='最长等待秒（默认 180）')
    p.add_argument('--dry-run', action='store_true', help='只报告该批准哪些 run，不真的批准')
    args = p.parse_args(argv)
    if not args.repo:
        p.error('缺 --repo，且环境变量 GITHUB_REPOSITORY 为空')
    return run(args)


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""报告 `main` 与 `dev` 的双向分叉 —— 让「跑的不是它」变得可发现（CNB #123）。

为什么需要它
------------
本仓的长期分支只有两条（`main` 稳定 / `dev` 集成），正常态是
**`main` 落后 `dev`，且 `main` 不领先**：发版 PR (`dev` → `main`) 把 `dev` 推上去，
所以「`main` 独有的提交数」应当恒为 0（或仅有发版本身的 merge commit）。

实测（2026-10-11）却是**双向分叉**：`main` 独有 15 个提交、`dev` 独有 20 个，
`git merge-base --is-ancestor origin/main origin/dev` 为 **false**。根因是两条功能分支
（`feat/github-issue-cnb-mirror` 与 `feat/2-cnb-github-backfill`）从**同一个 base**
分出后各自只投递到一侧分支 ⇒ `main` 拿到镜像链路、`dev` 拿到回写链路，**互不包含**。

后果不是理论风险：**crontab 只能挂在具体分支下**，`.cnb.yml` 挂在 `main`
⇒ 今天真正执行的是 `main` 那版策略，而「整改代码」可能躺在 `dev` 上——
**写完了，跑的不是它**，且没有任何信号提示这件事。这与 `issue-milestone-guard.yml`
「补挂里程碑后不自愈」同族。

本脚本把「靠人肉 `git log` 发现分叉」换成「一条命令问出来」。

判据
----
- **`main` 独有提交数 > 0** ⇒ 分叉（正常态恒为 0）；
- 分叉时列出**两侧各自的独有提交清单**（`--oneline`，超 LIMIT 截断）——
  只报数字修不了根因，救援的人需要能照抄的 SHA（CNB #118 断链卡面同诉求）；
- 列出**两侧互不包含**的「镜像 / 作业配置文件」（`.cnb.yml` + `.github/workflows/*.yml`）
  —— 这类文件决定「什么会被执行」，只在单侧存在就是 #123 记的那个病；
- 角色可切换（`--left` / `--right`），非本仓的 main/dev 布局也能用。

边界（有意为之）
----------------
- **纯离线**：只读本地 git，**不联网、不调 GitHub / CNB API**——
  分叉判定不该依赖网络，否则「网络不通 = 报告绿」又是一次静默降级；
- **只报告，不改动**：不 fetch、不 merge、不 push（fetch 会改 refs，且属于调用方决定）；
- **退出码**：0 = 未分叉；1 = 检出分叉（供 CI 当信号用）。调用方若不想要红灯，
  显式写 `|| true` —— 与 `check_mirror_refs.py` 同一口径。

用法
----
    # 默认比较 origin/main ← origin/dev
    python scripts/bridge/check_branch_divergence.py --report

    # 只看「哪些作业只在单侧」，不看提交计数
    python scripts/bridge/check_branch_divergence.py --report --jobs-only

    # 换一对分支（例如本地分支）
    python scripts/bridge/check_branch_divergence.py --report --left main --right dev --cwd /path/to/repo

    # 分叉时附带离线合并试算（git merge-tree，回答「发版会不会冲突」）
    python scripts/bridge/check_branch_divergence.py --report --explain

    # 报告落盘（供 notify_mirror_divergence.py 拼断链卡面）
    python scripts/bridge/check_branch_divergence.py --report --explain --out report-divergence.md
"""

from __future__ import annotations

import argparse
import subprocess
import sys

# 「决定什么会被执行」的文件：改了它们却没发版，等于改了不跑。
# 有意只收这两类 —— 业务代码落后不致命（下次发版跟上即可），
# 而作业配置落后会让**作业本身**按旧策略跑。
JOB_PATHSPECS = ('.cnb.yml', '.github/workflows')

# 独有提交清单的截断长度：分叉严重时一侧可能有几百个提交，
# 全列会把报告（与断链卡面）撑爆，救援照抄最近的足够定位。
COMMIT_LIST_LIMIT = 20


def _git(args: list[str], cwd: str | None = None) -> tuple[int, str]:
    r = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, (r.stdout or '').strip()


def _ref_exists(ref: str, cwd: str | None) -> bool:
    code, _ = _git(['rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}'], cwd)
    return code == 0


def count_unique(behind_ref: str, ahead_ref: str, cwd: str | None) -> int | None:
    """`ahead_ref` 相对 `behind_ref` 独有的提交数。取不到返回 None。"""
    code, out = _git(['rev-list', '--count', f'{behind_ref}..{ahead_ref}'], cwd)
    return int(out) if code == 0 and out.isdigit() else None


def list_side_only(left: str, right: str, cwd: str | None) -> tuple[list[str], list[str]]:
    """返回 (只在 left / 只在 right) 的作业配置文件。

    `git diff --name-status left right` 的标记语义（**方向敏感，别猜**）：
      - `D <path>` ⇒ 该文件在 `left` 有、`right` 没有 ⇒ **只在 left**；
      - `A <path>` ⇒ 该文件在 `right` 有、`left` 没有 ⇒ **只在 right**；
      - `M` / `R*` 等 ⇒ 两侧都有，不算「只在单侧」。

    这一步曾写错成「A 或 D 都算只在 right」，于是同一个文件在两个列表里各出现一次
    （`.cnb.yml` 与 `cnb-github-backfill.yml` 同时被报在两侧）—— 报告自相矛盾。
    判据方向错等于报告不可用，故此处按 `D`/`A` 分别归属。
    """
    code, out = _git(['diff', '--name-status', left, right, '--', *JOB_PATHSPECS], cwd)
    if code != 0:
        return [], []
    only_left: list[str] = []
    only_right: list[str] = []
    for line in out.splitlines():
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        status = parts[0]
        path = parts[-1]
        if status.startswith('D'):
            only_left.append(path)
        elif status.startswith('A'):
            only_right.append(path)
    return sorted(set(only_left)), sorted(set(only_right))


def list_unique_commits(behind_ref: str, ahead_ref: str, cwd: str | None, limit: int = COMMIT_LIST_LIMIT) -> list[str]:
    """`ahead_ref` 相对 `behind_ref` 的独有提交清单（`--oneline`，最新的在前）。

    跳过 merge commit：镜像断链场景里两侧各自的 merge commit 只是症状不是内容，
    列出来只会把真正该被 cherry-pick 的业务提交挤下去。截断到 `limit` 条，
    最后补一行「还有 N 条」的注记 —— 救援照抄清单，不需要全量。
    """
    code, out = _git(['log', '--oneline', '--no-decorate', '--no-merges', f'{behind_ref}..{ahead_ref}'], cwd)
    if code != 0 or not out:
        return []
    lines = out.splitlines()
    if len(lines) > limit:
        lines = lines[:limit] + [
            f'…（还有 {len(lines) - limit} 条，完整清单跑 `git log --oneline {behind_ref}..{ahead_ref}`）'
        ]
    return lines


def merge_dry_run(left: str, right: str, cwd: str | None) -> dict:
    """离线试算「把 right 合并进 left」会不会冲突（`git merge-tree`，不碰工作区）。

    回答 #123 卡面 §一 的问题：分叉之后，发版 PR（`dev` → `main`）还能不能干净合。
    退出码 0 = 可干净合并；1 = 有冲突（stdout 列冲突文件）；其余 = 试算本身失败。
    """
    code, out = _git(['merge-tree', '--write-tree', left, right], cwd)
    if code not in (0, 1):
        return {'ok': None, 'conflicts': []}
    conflicts = []
    if code == 1:
        # merge-tree --write-tree 的冲突段：`<mode> <sha> <path>` 之后是
        # `CONFLICT ( ... )` 行；这里只取「出现在输出里的路径」，够定位。
        for line in out.splitlines():
            parts = line.split('\t')
            if len(parts) == 2 and parts[1].strip():
                conflicts.append(parts[1].strip())
        conflicts = sorted(set(conflicts))
    return {'ok': code == 0, 'conflicts': conflicts}


def compute(left: str, right: str, cwd: str | None = None) -> dict:
    """把「谁落后谁、哪些作业只在单侧」算成结构化结果（纯函数，便于钉回归网）。"""
    left_jobs, right_jobs = list_side_only(left, right, cwd)
    return {
        'left': left,
        'right': right,
        'left_only': count_unique(right, left, cwd),
        'right_only': count_unique(left, right, cwd),
        'left_only_jobs': left_jobs,
        'right_only_jobs': right_jobs,
        'left_only_commits': list_unique_commits(right, left, cwd),
        'right_only_commits': list_unique_commits(left, right, cwd),
    }


def build_report(res: dict) -> str:
    left, right = res['left'], res['right']
    lo, ro = res['left_only'], res['right_only']
    diverged = bool(lo) or bool(ro)
    lines = [
        '## 分支分叉自检',
        '',
        f'- 比较：`{left}` ↔ `{right}`',
        f'- `{left}` 独有提交：**{lo}**',
        f'- `{right}` 独有提交：**{ro}**',
        '',
    ]
    if not diverged:
        lines.append(f'✅ 未分叉：`{left}` 是 `{right}` 的祖先（或两侧一致），发版不会丢东西。')
        return '\n'.join(lines)

    lines.append(f'⚠️ **已分叉**：两侧互不包含。正常态是 `{left}` 独有提交恒为 0。')
    lines.append('')
    for side, key, commits in (
        (left, 'left_only_commits', res.get('left_only_commits') or []),
        (right, 'right_only_commits', res.get('right_only_commits') or []),
    ):
        if commits:
            lines.append(f'**只在 `{side}` 上的提交**（需 cherry-pick 送回另一侧，照抄即可）：')
            lines.append('')
            lines.append('```text')
            lines.extend(commits)
            lines.append('```')
            lines.append('')
    for side, key, jobs in (
        (left, 'left_only_jobs', res['left_only_jobs']),
        (right, 'right_only_jobs', res['right_only_jobs']),
    ):
        if jobs:
            lines.append(f'**只在 `{side}` 上的作业配置**（改了不跑 / 跑了不是它）：')
            lines.append('')
            lines.extend(f'- `{p}`' for p in jobs)
            lines.append('')
    dry = res.get('merge_dry_run')
    if dry is not None:
        if dry['ok'] is None:
            lines.append('> ⚠️ 合并试算失败（`git merge-tree` 异常退出），冲突与否未知。')
        elif dry['ok']:
            lines.append(
                '> ✅ 试算：把 `dev` 合进 `main` **可干净合并**（离线 `git merge-tree`，未碰工作区）——尽快发版即可闭环。'
            )
        else:
            lines.append('> ⛔ 试算：发版合并**有冲突**，需先在 `dev` 解决：')
            lines.append('>')
            lines.extend(f'> - `{p}`' for p in dry['conflicts'])
        lines.append('')
    lines += [
        '> 处置：**发版**（`dev` → `main` 的 PR，head 必须是 `dev` 本身）。',
        '> 不要用「把功能分支 base 改成 main」消除时间差 —— 那正是本分叉的成因（见 AGENTS.md「PR 与 Review」）。',
    ]
    return '\n'.join(lines)


def run(args: argparse.Namespace) -> int:
    for ref in (args.left, args.right):
        if not _ref_exists(ref, args.cwd):
            print(f'❌ 取不到分支 `{ref}`（先 git fetch，或换 --left / --right）', file=sys.stderr)
            return 2
    res = compute(args.left, args.right, args.cwd)
    if args.jobs_only:
        res = {**res, 'left_only': None, 'right_only': None}
    diverged = bool(res['left_only']) or bool(res['right_only'])
    if args.explain and diverged:
        res['merge_dry_run'] = merge_dry_run(args.left, args.right, args.cwd)
    report = build_report(res)
    print(report)
    if args.out:
        from pathlib import Path

        Path(args.out).write_text(report + '\n', encoding='utf-8')
        print(f'\n📄 报告已写入 {args.out}')
    return 1 if diverged else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='报告 main / dev 的双向分叉（CNB #123）')
    p.add_argument('--report', action='store_true', help='输出 markdown 报告（默认行为）')
    p.add_argument('--left', default='origin/main', help='稳定分支（默认 origin/main）')
    p.add_argument('--right', default='origin/dev', help='集成分支（默认 origin/dev）')
    p.add_argument('--cwd', default=None, help='git 仓库路径（默认当前目录）')
    p.add_argument('--jobs-only', action='store_true', help='只看作业文件差异，不报提交数')
    p.add_argument(
        '--explain', action='store_true', help='分叉时离线试算发版合并会不会冲突（git merge-tree，不碰工作区）'
    )
    p.add_argument('--out', default=None, help='报告写入文件')
    return run(p.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())

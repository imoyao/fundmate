#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回向快进：把 GitHub `dev` 的最新 sha **快进**回 CNB `dev`（源 CNB #601，2026-10-19）。  # cross-repo-ref-allow

WHY 要有它
==========
CNB ↔ GitHub 之间的**搬运动作是单向的**：CNB 侧改动 → `merge-sync` → GitHub `dev`
（源 CNB #577）。GitHub 侧合入之后，CNB 的 `dev` **不会自己跟上** —— 于是：  # cross-repo-ref-allow

  - CNB 侧作者在**旧基**上开分支，推上去撞非快进被拒
    （`.cnb.yml` 功能分支同步段记着这个失败态：`(non-fast-forward)`，源 CNB #600）；  <!-- cross-repo-ref-allow -->
  - 「CNB `dev` 落后了多少」这件事**两侧都没有信号**，与 #269 的「三天零信号」同族。

本脚本补的就是那一步回向：**GitHub `dev` → CNB `dev`，只 FF、永不 force**。

判据（取数与 `check_cross_repo_dev_divergence.py` 共用同一套）
=============================================================
  | 形态 | 判定 | 动作 |
  |---|---|---|
  | 两侧 sha 相同 | 已一致 | 无动作 |
  | CNB sha 是 GitHub sha 的祖先 | GitHub 单侧领先 | **快进** `<gh-sha>:refs/heads/dev` |
  | GitHub sha 是 CNB sha 的祖先 | CNB 单侧领先 | 无动作（等 push 作业搬运），rc 0 |
  | 互不包含 | **真双向分叉** | 不推、rc 1，指向 `dev_converge.py` |
  | 祖先关系判不出来（对象缺失 / 不是 git 仓） | 拿不到输入 | rc 2，**不得**读成「无需回向」 |

退出码
======
    0 = 已一致 / 快进成功 / 未加 `--apply` 时判定可快进 / CNB 单侧领先
    1 = 真双向分叉（需人工收敛）
    2 = **拿不到输入**（fetch 失败 / ref 缺失 / 祖先关系判不出来）⇒ 结论不可信
    3 = **推送被拒**（构建身份无目标分支写权限 / 分支保护）

    1 与 3 分开，是为了让调用方（`.cnb.yml` 的 stage）能分别说清处置：
    「分叉」要人来合，「推不上去」要人去开权限 —— 两者的下一步动作完全不同。

⚠️ `2` 与 `0` 必须分得开：「拿不到」不等于「已对齐」（源 CNB #171 的失败态纪律）。
   把 2 读成 0，就是「一直绿、一直没干活」那种假绿。

⚠️ **永不 force**：回向 force 会冲掉 GitHub 侧尚未搬进 CNB 的提交，是**静默丢改动**。
   真分叉时的正确动作是**人工收敛**（`python scripts/bridge/dev_converge.py --apply` 列清单），
   不是抹平。

用法
====
    python scripts/bridge/ffback_cnb_dev.py                  # 只报告（默认 dry-run）
    python scripts/bridge/ffback_cnb_dev.py --apply           # 真推（FF）
    python scripts/bridge/ffback_cnb_dev.py --apply --cnb-url https://cnb.cool/duoduobei/fundmate.git
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_cross_repo_dev_divergence import (  # noqa: E402  （同目录，脚本非包）
    CNB_REF,
    DEFAULT_GITHUB_URL,
    GH_REF,
    build_report,
    divergence,
    fetch_branch,
)


def _git(args: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    r = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, (r.stdout or '').strip(), (r.stderr or '').strip()


def _ancestor_state(older_sha: str, newer_sha: str, cwd: str | None = None) -> bool | None:
    """`older_sha` 是否为 `newer_sha` 的祖先：`True` / `False` / `None`（**拿不到输入**）。

    `git merge-base --is-ancestor` 的退出码是三分：0 = 是、1 = 不是、其它（128）= 对象缺失 /
    不是 git 仓。**把 128 当成「不是祖先」是错的**——它会把「读不到」静默成一条正常结论
    （源 CNB #171：空 ≠ 没拿到）。故这里显式把「读不到」单独交出去。
    """
    code, _, _ = _git(['merge-base', '--is-ancestor', older_sha, newer_sha], cwd)
    if code in (0, 1):
        return code == 0
    return None


def plan(cnb_sha: str, gh_sha: str, cwd: str | None = None) -> str:
    """给出动作：`same` / `ff` / `cnb_ahead` / `diverged` / `unknown`。

    纯函数（只依赖 sha 与祖先关系），便于钉回归网。
    """
    if cnb_sha == gh_sha:
        return 'same'
    cnb_is_ancestor = _ancestor_state(cnb_sha, gh_sha, cwd)
    gh_is_ancestor = _ancestor_state(gh_sha, cnb_sha, cwd)
    if cnb_is_ancestor is None or gh_is_ancestor is None:
        return 'unknown'
    if cnb_is_ancestor:
        return 'ff'
    if gh_is_ancestor:
        return 'cnb_ahead'
    return 'diverged'


def push_fast_forward(target_url: str, branch: str, cwd: str | None = None) -> tuple[int, str, str]:
    """把已 fetch 到本地的 `GH_REF` 推到目标仓的 `branch`。

    **刻意不带 `--force` / `-f` / `+`**：远端自己会做快进判定，非快进会被拒（这正是护栏）。
    """
    return _git(['push', target_url, f'{GH_REF}:refs/heads/{branch}'], cwd)


def run(args: argparse.Namespace) -> int:
    cwd = args.cwd
    ok_cnb, err_cnb = fetch_branch(args.cnb_url, args.branch, CNB_REF, cwd)
    ok_gh, err_gh = fetch_branch(args.github_url, args.branch, GH_REF, cwd)
    if not ok_cnb or not ok_gh:
        detail = ') / ('.join([e for e in (err_cnb, err_gh) if e])
        print(
            f'❌ 拿不到输入：{detail} —— **本轮结论不可信**（不得读成「已对齐」，源 CNB #171）',
            file=sys.stderr,
        )
        return 2

    _, cnb_sha, _ = _git(['rev-parse', CNB_REF], cwd)
    _, gh_sha, _ = _git(['rev-parse', GH_REF], cwd)
    if not cnb_sha or not gh_sha:
        print(
            f'❌ 拿不到输入：fetch 成功但解不出 sha（CNB={cnb_sha or "?"} / GitHub={gh_sha or "?"}）'
            ' —— **本轮结论不可信**',
            file=sys.stderr,
        )
        return 2
    decision = plan(cnb_sha, gh_sha, cwd)
    # 机器可读摘要：供 `.cnb.yml` 的 stage 回显（人读日志时不必去数 sha）。
    print(f'FFBACK_DECISION={decision} FFBACK_CNB={cnb_sha[:12]} FFBACK_GH={gh_sha[:12]}')

    if decision == 'same':
        print(f'✅ 两侧 `{args.branch}` 已一致（{cnb_sha[:12]}）—— 无需回向')
        return 0

    if decision == 'unknown':
        print(
            '❌ 拿不到输入：两侧 sha 的祖先关系判不出来（对象缺失 / 不是 git 仓）'
            ' —— **本轮结论不可信**（不得读成「无需回向」）',
            file=sys.stderr,
        )
        return 2

    if decision == 'cnb_ahead':
        print(f'ℹ️ CNB 单侧领先（GitHub `{args.branch}` 是它的祖先）：无需回向，等 push 作业把 CNB 侧搬过去即可')
        return 0

    if decision == 'diverged':
        print(build_report(divergence(cnb_sha, gh_sha, CNB_REF, GH_REF, cwd)))
        print(
            '❌ 真双向分叉：**本脚本不处理**（它只做快进，不 force 抹平）。'
            '处置：`python scripts/bridge/dev_converge.py --apply` 列出冲突清单后人工收敛一次。'
        )
        return 1

    # decision == 'ff'
    cmd = ['git', 'push', args.cnb_url, f'{GH_REF}:refs/heads/{args.branch}']
    if not args.apply:
        print(f'ℹ️ GitHub 单侧领先，快进可成（**dry-run，未推送**）：{" ".join(cmd)}')
        print('   —— 加 `--apply` 才真的推；本脚本永不 force。')
        return 0

    code, out, err = push_fast_forward(args.cnb_url, args.branch, cwd)
    if code != 0:
        print(err or out, file=sys.stderr)
        print(
            '❌ 回向推送被拒 —— 常见原因：构建身份对 CNB 该分支无写权限，或该分支有保护规则。\n'
            '   处置：人工确认后决定「放开作业写权限」还是「改由 GitHub 侧推送」；'
            '**不要**改成 force（会静默丢改动）。',
            file=sys.stderr,
        )
        return 3
    print(f'✅ 已把 CNB `{args.branch}` 快进到 GitHub 侧 {gh_sha[:12]}')
    if out:
        print(out)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description='把 GitHub dev 快进回 CNB dev（只 FF、永不 force；源 CNB #601）'  # cross-repo-ref-allow
    )
    p.add_argument('--apply', action='store_true', help='真的推送（默认只 dry-run 报告）')
    p.add_argument('--cnb-url', default=None, help='CNB 远程 URL（默认 origin 的 URL）')
    p.add_argument('--github-url', default=DEFAULT_GITHUB_URL, help='GitHub 远程 URL')
    p.add_argument('--branch', default='dev', help='分支名（默认 dev）')
    p.add_argument('--cwd', default=None, help='git 仓库路径（默认当前目录）')
    args = p.parse_args(argv)
    if not args.cnb_url:
        code, url, _ = _git(['remote', 'get-url', 'origin'], args.cwd)
        args.cnb_url = url if code == 0 and url else 'https://cnb.cool/duoduobei/fundmate.git'
    return run(args)


if __name__ == '__main__':
    sys.exit(main())

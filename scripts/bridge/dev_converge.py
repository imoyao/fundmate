#!/usr/bin/env python3
"""跨仓 `dev` 分叉的**收敛作业**：把 GitHub `dev` 合成一条本地分支，供人工解冲突
（源 CNB #269，2026-10-14）。  <!-- cross-repo-ref-allow -->

为什么需要它
------------
`check_cross_repo_dev_divergence.py`（同目录）只**报警**：两侧 `dev` 双向分叉、
同步会一直空转。它是对的，但**报警不等于解决** —— 死锁仍在，且每天多欠一笔。

本脚本补上「报警之后那一脚」，且**刻意只做安全的那半**：

| 它做 | 它不做 |
|---|---|
| 从 `dev` 切一条**收敛分支**（`rescue/dev-converge-<date>`） | ❌ 不直接动 `dev` |
| 把 GitHub `dev` 合进来 | ❌ 不自动解冲突（冲突停下报人） |
| 打印冲突文件清单 | ❌ 不 push、不开 PR（调用方决定） |

即：**它把「切分支 + 合 + 数冲突」这三步机械活做完，把判断留给人。**

为什么不能自动解冲突
--------------------
实测两侧冲突面覆盖 `.cnb.yml` / `AGENTS.md` / `ci.yml` / `docs/spec/*` 等
**规范与流水线文件**。这些地方的冲突解错 = 悄悄改掉治理规则（比代码冲突贵得多），
故 `--resolve` 之类的一键开关**有意不提供**。

方向必须先定
------------
`--base cnb`（默认）：以 CNB `dev` 为基线，把 GitHub `dev` 合进来 ⇒ 收敛后推 GitHub；
`--base github`       ：以 GitHub `dev` 为基线，把 CNB `dev` 合进来 ⇒ 收敛后推 CNB。

两个方向**结果不同**（谁的 merge commit 在上、冲突以谁为准），必须先与人确认。
不传就按默认走并在输出里**写明用了哪一侧**，避免事后不知道这条分支是怎么来的。

用法
----
    # 演练：只看会不会冲突、有哪些冲突文件（不建分支、不改工作区）
    python scripts/bridge/dev_converge.py --dry-run

    # 真正执行：建收敛分支 + merge（冲突则停下并列出文件）
    python scripts/bridge/dev_converge.py --apply

    # 指定方向与分支名
    python scripts/bridge/dev_converge.py --apply --base github \
        --branch rescue/dev-converge-2026-10-14

退出码：0 = 收敛分支已就绪（无冲突）；1 = 有冲突，需人工解；
        2 = 拿不到输入（fetch / ref 缺失）——**结论不可信**，不得当作「没问题」。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date

DEFAULT_GITHUB_URL = 'https://github.com/imoyao/fundmate.git'
GH_REF = 'refs/cross-converge/gh-dev'
CNB_REF = 'refs/cross-converge/cnb-dev'


def _git(args: list[str], cwd: str | None = None) -> tuple[int, str]:
    r = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, (r.stdout or '').strip()


def fetch_branch(url: str, branch: str, dest_ref: str, cwd: str | None = None) -> tuple[bool, str]:
    code, out = _git(['fetch', '--quiet', url, f'{branch}:{dest_ref}'], cwd)
    if code != 0:
        return False, out or f'git fetch {url} {branch} 失败'
    return True, ''


def conflict_files(cwd: str | None = None) -> list[str]:
    code, out = _git(['diff', '--name-only', '--diff-filter=U'], cwd)
    if code != 0:
        return []
    return [line for line in out.splitlines() if line.strip()]


def plan(base: str, branch: str, gh_ref: str = GH_REF, cnb_ref: str = CNB_REF) -> dict:
    """把「以谁为基线、把谁合进来」这对选择算清楚。纯函数，便于钉回归网。"""
    if base == 'github':
        return {'base_ref': gh_ref, 'base_name': 'GitHub', 'merge_ref': cnb_ref, 'merge_name': 'CNB', 'branch': branch}
    return {'base_ref': cnb_ref, 'base_name': 'CNB', 'merge_ref': gh_ref, 'merge_name': 'GitHub', 'branch': branch}


def build_report(p: dict, *, created: bool, conflicts: list[str]) -> str:
    lines = ['## 跨仓 dev 收敛', '']
    lines.append(f'- 基线方向：以 **{p["base_name"]} `dev`** 为基线，合入 **{p["merge_name"]} `dev`**')
    lines.append(f'- 收敛分支：`{p["branch"]}`')
    lines.append('')
    if not created:
        lines.append('(')
        lines.append('演练模式：未建分支、未改工作区。加 `--apply` 执行。')
        lines.append(')')
        return '\n'.join(lines)
    if not conflicts:
        lines.append('✅ 收敛分支已就绪，**无冲突**。')
        lines.append('')
        lines.append('下一步（人工）：')
        lines.append(f'1. `git checkout {p["branch"]}` 复核 diff；')
        lines.append('2. 走 PR 合回目标 `dev`（**不直接 push dev**）；')
        lines.append('3. 合入后手动触发一次 git-sync，把收敛结果推过去 ⇒ 死锁解开。')
        return '\n'.join(lines)
    lines.append(f'⚠️ **有 {len(conflicts)} 个文件冲突**，需人工逐处解（脚本刻意不自动解）。')
    lines.append('')
    for f in conflicts:
        lines.append(f'- `{f}`')
    lines.append('')
    lines.append('解完后 `git add` + `git commit`，再走 PR。')
    return '\n'.join(lines)


def run(args: argparse.Namespace) -> int:
    cwd = args.cwd
    ok_cnb, err_cnb = fetch_branch(args.cnb_url, args.branch, CNB_REF, cwd)
    ok_gh, err_gh = fetch_branch(args.github_url, args.branch, GH_REF, cwd)
    if not ok_cnb or not ok_gh:
        msg = ') / ('.join([e for e in (err_cnb, err_gh) if e])
        print(f'❌ 拿不到输入：{msg}', file=sys.stderr)
        return 2

    branch_name = args.out_branch or f'rescue/dev-converge-{date.today().isoformat()}'
    p = plan(args.base, branch_name)
    if args.dry_run or not args.apply:
        print(build_report(p, created=False, conflicts=[]))
        return 0

    code, _ = _git(['rev-parse', '--verify', '--quiet', branch_name], cwd)
    if code == 0:
        print(
            f'❌ 分支 `{branch_name}` 已存在——换一个 `--out-branch` 名字，或先处理掉它（本脚本不覆盖已有分支）。',
            file=sys.stderr,
        )
        return 2

    code, out = _git(['checkout', '-b', branch_name, p['base_ref']], cwd)
    if code != 0:
        print(f'❌ 建分支失败：{out}', file=sys.stderr)
        return 2

    code, out = _git(['merge', '--no-edit', p['merge_ref']], cwd)
    conflicts = conflict_files(cwd)
    print(build_report(p, created=True, conflicts=conflicts))
    return 1 if conflicts else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='dev 分叉收敛：建 rescue 分支并合入另一侧（源 CNB #269）')
    ap.add_argument('--apply', action='store_true', help='真正执行（默认演练）')
    ap.add_argument('--dry-run', action='store_true', help='演练（默认行为）')
    ap.add_argument('--base', choices=['cnb', 'github'], default='cnb', help='以哪一侧为基线（默认 cnb）')
    ap.add_argument('--out-branch', default=None, help='收敛分支名（默认 rescue/dev-converge-<date>）')
    ap.add_argument('--branch', default='dev', help='被收敛的分支名（默认 dev）')
    ap.add_argument('--cnb-url', default=None, help='CNB 远程 URL（默认 origin 的 URL）')
    ap.add_argument('--github-url', default=DEFAULT_GITHUB_URL, help='GitHub 远程 URL')
    ap.add_argument('--cwd', default=None, help='git 仓库路径（默认当前目录）')
    args = ap.parse_args(argv)
    if not args.cnb_url:
        code, url = _git(['remote', 'get-url', 'origin'], args.cwd)
        args.cnb_url = url if code == 0 and url else 'https://cnb.cool/duoduobei/fundmate.git'
    return run(args)


if __name__ == '__main__':
    sys.exit(main())

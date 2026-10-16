#!/usr/bin/env python3
"""报告 **CNB 的 `dev` 与 GitHub 的 `dev`** 是否已分叉（源 CNB #269，2026-10-14）。  # cross-repo-ref-allow

为什么单独需要它
----------------
`check_branch_divergence.py` 比的是**同一个仓库内部**的 `main ← dev`（CNB #123）。
而 2026-10-11 ~ 10-14 真正出事的是**跨仓**那一维：CNB `dev` 停了、GitHub `dev` 一直在走，
两边各自长出对方没有的提交，**三天没有任何信号**。等到有人发现时：

    CNB dev 独有（GitHub 没有）  → 30 个真提交
    GitHub dev 独有（CNB 没有）  → 89 个真提交

后果不是理论风险 —— 它是**死锁**：git-sync 的 push 不开 `force`（对，是护栏），
于是「CNB dev → GitHub dev」永远是非快进、永远被拒；pull 又拉不动。两边都不动。

一句话：**「分叉了几笔」这个数在仓内自检里问不出来，因为另一半在另一个仓库。**

判据（与 #179 同源，**只用 `git cherry` 补丁等价**）
-----------------------------------------------------
对同一对分支做**双向**内容级判据：

    git cherry <gh/dev>   <cnb/dev>   # 有 `+` ⇒ CNB 侧有 GitHub 拿不到的改动
    git cherry <cnb/dev>  <gh/dev>    # 有 `+` ⇒ GitHub 侧有 CNB 拿不到的改动

- **两侧都为空** ⇒ 未分叉，只是「一边落后一点」⇒ **不红**（放行正常落后）；
- **只有一侧有 `+`** ⇒ 单侧领先 ⇒ 这是**正常的**（比如 GitHub 先合了 PR，CNB 还没拉）
  ⇒ **不红**，但打印一行提示「可通过 pull 收敛」；
- **两侧都有 `+`** ⇒ **真双向分叉**（谁也合不上谁）⇒ **红**。

⚠️ 不用 `git diff`：交叉合并下它对「一边落后」也非空 ⇒ 假红（#167 已实测 7 个假阳性）。
⚠️ 不用「一侧独有提交数 > 0」：落后一侧必然 > 0 ⇒ 又是假红（#179 已回滚过一版）。

「拿不到输入」不得降级成正常
----------------------------
`git fetch` 失败（网络 / 无权限）、或任一 ref 取不到 ⇒ 打印「拿不到输入」并**返回 2**，
**不得**返回 0。这条是 #171 / #269 反复踩过的假绿形态：拉不到数据时报「已对齐」。

边界（有意为之）
----------------
- 会 **fetch**（两个 remote 的 `dev`），因为要跨仓比较——这与仓内自检「纯离线」不同，
  故**不挂进 per-PR 的 `ci.yml`**（CI 里没有 GitHub 凭据，且不该让 PR 门禁依赖外网）。
  它挂在 `.cnb.yml` 的收尾自检里（那里网络与凭据都具备），只报告不拦构建；
- **只报告，不改动**：不 merge、不 push、不 rebase。

用法
----
    # 默认：CNB=origin/dev（本地 origin），GitHub=https://github.com/imoyao/fundmate.git
    python scripts/bridge/check_cross_repo_dev_divergence.py --report

    # 指定两侧 URL（两个都给了才 fetch，否则只读现有 ref）
    python scripts/bridge/check_cross_repo_dev_divergence.py --report \
        --cnb-url https://cnb.cool/duoduobei/fundmate.git \
        --github-url https://github.com/imoyao/fundmate.git

退出码：0 = 未分叉；1 = 真双向分叉；2 = 拿不到输入（结论不可信）。
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from check_branch_divergence import content_ahead  # noqa: E402  （同目录，脚本非包）

DEFAULT_GITHUB_URL = 'https://github.com/imoyao/fundmate.git'
# fetch 到本地的临时 ref（**不污染** origin/*，也不依赖调用方的 remote 命名）。
CNB_REF = 'refs/cross-check/cnb-dev'
GH_REF = 'refs/cross-check/gh-dev'


def _git(args: list[str], cwd: str | None = None) -> tuple[int, str]:
    r = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, (r.stdout or '').strip()


def fetch_branch(url: str, branch: str, dest_ref: str, cwd: str | None = None) -> tuple[bool, str]:
    """把 `url` 的 `branch` 取到 `dest_ref`。返回 (是否成功, 错误信息)。"""
    code, out = _git(['fetch', '--quiet', url, f'{branch}:{dest_ref}'], cwd)
    if code != 0:
        return False, out or f'git fetch {url} {branch} 失败'
    return True, ''


def divergence(cnb_sha: str, gh_sha: str, cnb_ref: str, gh_ref: str, cwd: str | None) -> dict:
    """双向内容级判据（`git cherry` 补丁等价）。纯函数，便于钉回归网。

    返回：
      - cnb_only / gh_only：各自的 `+` 行 sha 列表；
      - cnb_ahead / gh_ahead：该侧是否有 `right` 拿不到的改动；
      - diverged：**两侧都有**（真双向分叉）；
      - available：判据是否拿到了输入（任一取不到 ⇒ False）。
    """
    cnb_only = content_ahead(cnb_ref, gh_ref, cwd)
    gh_only = content_ahead(gh_ref, cnb_ref, cwd)
    if not cnb_only.get('available') or not gh_only.get('available'):
        return {'available': False, 'cnb_ahead': False, 'gh_ahead': False, 'diverged': False}
    cnb_ahead = bool(cnb_only.get('has_only_left'))
    gh_ahead = bool(gh_only.get('has_only_left'))
    return {
        'available': True,
        'cnb_sha': cnb_sha,
        'gh_sha': gh_sha,
        'cnb_only': list(cnb_only.get('only_left_commits') or []),
        'gh_only': list(gh_only.get('only_left_commits') or []),
        'cnb_ahead': cnb_ahead,
        'gh_ahead': gh_ahead,
        'diverged': cnb_ahead and gh_ahead,
    }


def build_report(res: dict) -> str:
    if not res.get('available'):
        return (
            '## 跨仓 dev 分叉自检\n\n'
            '⚠️ **拿不到输入**（fetch 失败或 ref 缺失）——**本轮结论不可信**，不得据此认为「已对齐」。\n'
            '（#171 / #269：空 ≠ 没拿到。拉不到数据时报「已对齐」是假绿。）'
        )
    lines = ['## 跨仓 dev 分叉自检（CNB `dev` ↔ GitHub `dev`）', '']
    lines.append(f'- CNB   `dev` → `{res["cnb_sha"][:8]}`')
    lines.append(f'- GitHub `dev` → `{res["gh_sha"][:8]}`')
    lines.append('')
    if not res['diverged']:
        if res['cnb_ahead']:
            lines.append(f'✅ 未分叉（**CNB 单侧领先** {len(res["cnb_only"])} 笔）：等 push 作业收敛即可。')
        elif res['gh_ahead']:
            lines.append(f'✅ 未分叉（**GitHub 单侧领先** {len(res["gh_only"])} 笔）：等 pull 作业收敛即可。')
        else:
            lines.append('✅ 未分叉：两侧内容一致。')
        return '\n'.join(lines)
    lines.append('❌ **双向分叉**：两侧各自握有对方没有的改动 ⇒ 谁都无法快进谁，同步会一直空转。')
    lines.append('')
    lines.append(f'- CNB 独有（GitHub 拿不到）：**{len(res["cnb_only"])}** 笔')
    lines.append(f'- GitHub 独有（CNB 拿不到）：**{len(res["gh_only"])}** 笔')
    lines.append('')
    lines.append('处置：需要一次**人工收敛**（以某一侧为基线合并，解冲突后推平）——')
    lines.append('不处理的话，差异只会逐日累积。详见 `docs/dev/github-cnb-mirror.md` §16。')
    return '\n'.join(lines)


def run(args: argparse.Namespace) -> int:
    cwd = args.cwd
    ok_cnb, err_cnb = fetch_branch(args.cnb_url, args.branch, CNB_REF, cwd)
    ok_gh, err_gh = fetch_branch(args.github_url, args.branch, GH_REF, cwd)
    if not ok_cnb or not ok_gh:
        msg = ') / ('.join([e for e in (err_cnb, err_gh) if e])
        print(f'❌ 拿不到输入：{msg}', file=sys.stderr)
        print(build_report({'available': False}))
        return 2
    _, cnb_sha = _git(['rev-parse', '--short=12', CNB_REF], cwd)
    _, gh_sha = _git(['rev-parse', '--short=12', GH_REF], cwd)
    res = divergence(cnb_sha, gh_sha, CNB_REF, GH_REF, cwd)
    if not res.get('available'):
        print(build_report(res))
        return 2
    print(build_report(res))
    return 1 if res['diverged'] else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='报告 CNB dev 与 GitHub dev 是否已双向分叉（源 CNB #269）')  # cross-repo-ref-allow
    p.add_argument('--report', action='store_true', help='输出 markdown 报告（默认行为）')
    p.add_argument('--cnb-url', default=None, help='CNB 远程 URL（默认 origin 的 URL）')
    p.add_argument('--github-url', default=DEFAULT_GITHUB_URL, help='GitHub 远程 URL')
    p.add_argument('--branch', default='dev', help='比较的分支名（默认 dev）')
    p.add_argument('--cwd', default=None, help='git 仓库路径（默认当前目录）')
    args = p.parse_args(argv)
    if not args.cnb_url:
        code, url = _git(['remote', 'get-url', 'origin'], args.cwd)
        args.cnb_url = url if code == 0 and url else 'https://cnb.cool/duoduobei/fundmate.git'
    return run(args)


if __name__ == '__main__':
    sys.exit(main())

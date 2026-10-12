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
- 列出**两侧互不包含**的「镜像 / 作业配置文件」（`.cnb.yml` + `.github/workflows/*.yml`）
  —— 这类文件决定「什么会被执行」，只在单侧存在就是 #123 记的那个病；
- 角色可切换（`--left` / `--right`），非本仓的 main/dev 布局也能用。

根因诊断（`--explain`，2026-10-11 补）
---------------------------------------
首轮只报「分叉了几个提交、哪些作业只在单侧」，**答不出「为什么分叉」**——
而卡面 §一 建议 3 的原话是：

> 为什么 `dev` 会完全不含 `main` 的这一个 commit？……**需要先答这个，
> 否则发版完还会再分叉一次。**

本仓是**跨平台双仓镜像**（GitHub `imoyao/fundmate` ↔ CNB `duoduobei/fundmate`），
两侧各自推进——**这是分叉得以发生的背景**（不是某一次操作失误）。

`--explain` 给两件**可证**的事：① 列出 `main` 独有的提交（短号 + 主题），来路由人判断；
② 离线试算「发版会不会冲突、冲突哪几个文件」（`git merge-tree`，不碰工作区）。

**它有意不判断「哪个提交来自 GitHub、哪个来自 CNB」**——实测三条路（提交信息启发式 /
`refs/fetched` / `sync/mirror` 分支）都答不了这个问题，猜错会让报告指向错误的处置。
详见 `explain()` 的 docstring。

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
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

# 「决定什么会被执行」的文件：改了它们却没发版，等于改了不跑。
# 有意只收这两类 —— 业务代码落后不致命（下次发版跟上即可），
# 而作业配置落后会让**作业本身**按旧策略跑。
JOB_PATHSPECS = ('.cnb.yml', '.github/workflows')


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
    }


def explain(left: str, right: str, cwd: str | None = None) -> dict:
    """列出 `left`（默认 main）独有的提交，并**只报可证的事实**。

    为什么不做「这是 GitHub 来的 / 这是 CNB 推的」自动归类：**git 数据答不了这个问题**。
    实测过三条路都不成立（2026-10-11）：
      - 提交信息启发式 —— `feat(detail): …（#2029 卡 B）` 是 GitHub 侧推的，
        而 `docs(api): …（#2029 卡 B）` 同批同源，没有任何标记能区分；
      - `refs/fetched/*` —— 它标的是「该提交**被合进** CNB 时 fetch 过」，
        `6c97c259`（跨仓同步 merge）在内、它上游的 GitHub 提交全不在，反着来；
      - `sync/mirror` 分支 —— 是另一条 lineage，不含这批提交。

    **猜错的代价是报告指向错误的处置**（该发版的被当成纪律违规，或反之），
    比「不给结论」坏得多。故这里只给两件可证的事：

      1. 逐个列出 `left` 独有提交（短号 + 主题）—— 人来判断来路；
      2. 给出**发版是否安全**的可证判据：把 `left` 合进 `right` 是否会产生冲突
         （用 `git merge-tree` 离线试算，不写工作区）。

    这与 `check_branch_divergence.py` 的既定口径一致：**只报告，不猜**。
    """
    code, out = _git(['log', '--format=%h\t%s', f'{right}..{left}'], cwd)
    commits = []
    if code == 0:
        for line in out.splitlines():
            if '\t' in line:
                short, subject = line.split('\t', 1)
                commits.append({'short': short, 'subject': subject})
    return {'commits': commits, 'merge_trial': _merge_trial(left, right, cwd)}


def _merge_trial(left: str, right: str, cwd: str | None) -> dict:
    """离线试算「发版会不会冲突」——即**把 `right` 合进 `left`**（`git merge-tree`，不碰工作区）。

    方向别搞反：`git merge-tree <A> <B>` 的语义是「把 B 合进 A」。
    发版 PR 是 `dev` → `main`（`right` → `left`），故传参为 `merge-tree left right`。
    传反了算出来的是「main 合进 dev」的冲突，与发布 PR 无关。

    `--write-tree` 是 git 2.38+ 的形态。取不到 base 时返回 `unknown` ——
    **不猜**，报告里明写「试算不可用」。
    """
    code, base = _git(['merge-base', left, right], cwd)
    if code != 0 or not base:
        return {'status': 'unknown', 'reason': '取不到 merge-base'}
    code, out = _git(['merge-tree', '--write-tree', '--name-only', left, right], cwd)
    if code == 0:
        return {'status': 'clean', 'base': base[:8], 'conflicts': []}
    # `--write-tree` 的首行是**试算结果的 tree hash**（40 位十六进制），不是文件名；
    # 其余行才是冲突路径。不滤掉它，报告里就会混进一条谁也看不懂的哈希。
    conflicts = [
        ln.strip()
        for ln in out.splitlines()
        if ln.strip()
        and not re.fullmatch(r'[0-9a-f]{40}', ln.strip())
        and not ln.startswith(('Auto-merging', 'CONFLICT'))
    ]
    return {'status': 'conflict', 'base': base[:8], 'conflicts': conflicts[:20]}


def build_explanation(res: dict, exp: dict) -> str:
    """把「`left` 独有提交清单 + 发版试算」写成给人看的结论段。"""
    left, right = res['left'], res['right']
    commits = exp.get('commits') or []
    trial = exp.get('merge_trial') or {}
    lines = ['', f'### `{left}` 独有提交（{len(commits)} 个，逐个看）', '']
    if not commits:
        lines.append(f'（`{left}` 没有独有提交）')
        return '\n'.join(lines)
    lines += [f'- `{c["short"]}` {c["subject"]}' for c in commits]
    lines += [
        '',
        f'### 发版试算（`{right}` → `{left}`，即发布 PR 的方向）',
        '',
        f'试算命令：`git merge-tree --write-tree --name-only {right} {left}`（**离线**，不碰工作区）。',
        '',
    ]
    status = trial.get('status')
    if status == 'clean':
        lines.append(f'✅ **可干净合并**（试算 base `{trial.get("base")}`）——发版不会撞冲突。')
    elif status == 'conflict':
        lines.append(f'⚠️ **会冲突**（试算 base `{trial.get("base")}`，{len(trial.get("conflicts") or [])} 个文件）：')
        lines += [f'- `{f}`' for f in (trial.get('conflicts') or [])]
        lines.append('')
        lines.append('冲突文件逐个消解后再提发布 PR。')
    else:
        lines.append(f'❓ **试算不可用**：{trial.get("reason")}（本环境 git 太旧或缺 ref）——人工判。')
    lines += [
        '',
        '> 本段**不猜**「哪个提交来自 GitHub、哪个来自 CNB」：实测提交信息、`refs/fetched`、',
        '> `sync/mirror` 三条路都答不了这个问题（见 `explain()` docstring）。',
        '> 来路由人看上面这份清单判断；机器只负责把「发版会不会冲突」算出来。',
    ]
    return '\n'.join(lines)


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
    for side, key, jobs in (
        (left, 'left_only_jobs', res['left_only_jobs']),
        (right, 'right_only_jobs', res['right_only_jobs']),
    ):
        if jobs:
            lines.append(f'**只在 `{side}` 上的作业配置**（改了不跑 / 跑了不是它）：')
            lines.append('')
            lines.extend(f'- `{p}`' for p in jobs)
            lines.append('')
    lines += [
        '> 处置：**发版**（`dev` → `main` 的 PR，head 必须是 `dev` 本身）。',
        '> 不要用「把功能分支 base 改成 main」消除时间差 —— 那正是本分叉的成因（见 AGENTS.md「PR 与 Review」）。',
    ]
    return '\n'.join(lines)


def run(args: argparse.Namespace) -> int:
    missing = [ref for ref in (args.left, args.right) if not _ref_exists(ref, args.cwd)]
    if missing:
        # 「分支不存在」与「分叉」是两件事，但都会让本自检失效，且**都不该静默通过**。
        # 尤其 `origin/dev` 整体消失（2026-10-12 实测：CNB 侧 53 个分支里没有 dev）
        # 意味着「功能分支 → dev」这条流程的落点没了 —— 比「分叉了几个提交」严重得多，
        # 而旧版只打一行 terse 的「先 git fetch」就退出 2，容易被当成环境噪音滑过去。
        print(f'❌ 取不到分支：{", ".join(f"`{r}`" for r in missing)}', file=sys.stderr)
        print(
            '   可能是 ① 没 fetch（先 `git fetch origin`）；② 分支被删/改名。\n'
            '   若是 `origin/dev` 不存在：本仓长期分支只有 `dev` / `main`，'
            '`dev` 消失意味着功能分支无处可合，须先恢复它再谈分叉。',
            file=sys.stderr,
        )
        return 2
    res = compute(args.left, args.right, args.cwd)
    if args.jobs_only:
        res = {**res, 'left_only': None, 'right_only': None}
    diverged = bool(res['left_only']) or bool(res['right_only'])
    report = build_report(res)
    # `getattr` 默认 False：`run()` 也被测试直接调用（`argparse.Namespace` 手搓），
    # 新加的可选开关不该让老调用点崩。
    if getattr(args, 'explain', False) and diverged:
        # 卡面 §一 建议 3：光知道「分叉了几个」修不了根因 —— 得答「为什么分叉」。
        report += build_explanation(res, explain(args.left, args.right, args.cwd))
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
        '--explain',
        action='store_true',
        help='检出分叉时，列出稳定分支独有的提交并离线试算发版冲突（答「为什么会分叉」）',
    )
    p.add_argument('--out', default=None, help='报告写入文件')
    return run(p.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())

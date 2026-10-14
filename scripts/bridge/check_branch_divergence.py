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

判据（2026-10-14 重写，源 CNB #179）
-------------------------------------
两个旧口径都产生过**假红**，各自修掉一层：

1. 「**`main` 独有提交数 > 0 ⇒ 分叉**」——发版 PR 必然给 `main` 留一个 merge commit，
   而它不引入任何内容 ⇒ **每发一次版红一次**；
2. 「**`git diff main dev` 非空 ⇒ 分叉**」——diff 是**双向**的，非空既可能是
   「`main` 有 `dev` 拿不到的」，也可能是「`dev` 更新、`main` 停在旧版」。
   本仓 2026-10-14 实测正是后者：`main` 停在发版时的版本、`dev` 往前走了 2 个提交，
   7 个文件的 diff 全是 `main` **更旧**，一条「`main` 独有内容」都没有，却报红。

**现行判据**（只认「`main` 有没有 `dev` 拿不到的代码」，即用户口径）：

- 先看祖先关系：`main` 是 `dev` 的祖先 ⇒ 差异全是 `dev` 领先 ⇒ **绿**；
- 互不包含时**逐文件判**：`main` 侧那个版本（blob）在 `dev` 的历史里出现过吗？
  - 出现过 ⇒ `dev` 曾经有过、`main` 停在旧版 ⇒ **滞后，不算独有**；
  - 从未出现 ⇒ `main` 上凭空长出来的 ⇒ **独有 ⇒ 红**（这才是要拦的）；
- 拿不到任一层的 git 结果 ⇒ 退出码 2 并**明说判据不可用**（「拿不到 ≠ 正常」，#171）。

另保留：列出**两侧互不包含**的「镜像 / 作业配置文件」（`.cnb.yml` +
`.github/workflows/*.yml`）—— 这类文件决定「什么会被执行」，只在单侧存在就是 #123 记的病；
角色可切换（`--left` / `--right`），非本仓的 main/dev 布局也能用。

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


def content_ahead(left: str, right: str, cwd: str | None = None) -> dict:
    """**内容级**判据：`left` 上有没有 `right` **拿不到**的内容（CNB #179）。

    为什么不能只看提交数：发版 PR（`dev` → `main`）**必然**给 `left` 留一个 merge commit，
    而它**不引入任何新内容**。旧版 `count_unique(left) > 0` 把这种**正常的发版节点**也
    报成「已分叉」，于是每发一次版就红一次 —— 红却不指向任何还需动手的事，是**假红**
    （与 #118 的假绿同族）。

    为什么也不能只看 `git diff left right` 非空（**这是本卡修掉的第二个坑**）：
    `git diff` 的差异是**双向**的，非空既可能是「`left` 有 `right` 拿不到的」，
    也可能是「`right` 更新、`left` 停在旧版」。本仓 2026-10-14 实测就是后者：
    `main` 停在发版时的旧版、`dev` 往前走了 2 个提交，7 个文件的 diff 全部是
    **`main` 更旧**（numstat 里删除数远大于新增），一条「`main` 独有内容」都没有，
    旧实现却报红 —— 又一处假红。

    判据（三层，逐层收紧，每层都只报可证的事实）
    -------------------------------------------
    1. **祖先关系**（最快、最干净）：
       - `left` 是 `right` 的祖先 ⇒ 差异全是「`right` 领先」⇒ **没有 `left` 独有内容**；
       - `right` 是 `left` 的祖先 ⇒ 差异全是「`left` 独有」⇒ 全部算独有；
    2. **互不包含时逐文件判**（本仓常态：`left` 停在旧版 + `right` 往前走了）：
       取 `git diff --name-only` 的每个路径，问「`left` 侧那个版本（blob）
       在 `right` 的历史里出现过吗」（`git log --find-object=<blob> <right> -- <path>`）：
       - 出现过 ⇒ 那是 `right` 曾经有过、`left` 停在旧版 ⇒ **不算独有**；
       - 从未出现过 ⇒ `left` 上凭空长出来的 ⇒ **算独有**（这才是要拦的形态）。
    3. 拿不到任何一层的结果时，`available=False` **明说判据不可用**——
       不猜、不降级成「正常」（「拿不到输入 ≠ 输入为空」，#171 教训）。
    """
    code, out = _git(['diff', '--name-only', left, right], cwd)
    if code != 0:
        return {'available': False, 'reason': f'git diff 退出码 {code}'}
    changed = [ln.strip() for ln in out.splitlines() if ln.strip()]
    left_is_ancestor = _git(['merge-base', '--is-ancestor', left, right], cwd)[0] == 0
    right_is_ancestor = _git(['merge-base', '--is-ancestor', right, left], cwd)[0] == 0

    if not changed:
        only_left, unique = [], []
    elif left_is_ancestor:
        # 快路径（**不是判据的一部分**）：`left` 是 `right` 的祖先时，差异必然全在 `right`
        # 那边 ⇒ `left` 不可能有 `right` 拿不到的内容，可跳过下面的逐文件历史查询。
        #
        # ⚠️ 这条分支**可以被删掉而不改变行为** —— 走下面的逐文件分支会得到同样结果
        # （`left` 侧的每个版本都在 `right` 历史里 ⇒ 全落 `superseded`）。回退探针实测
        # 把它改成 `elif False:` 后**一条用例都不红**，即它是死代码级别的短路优化。
        # 按 AGENTS.md「探针咬不住的分支，往往在做假装的工作」：处置是**写明它是优化**，
        # 而不是给它补一条测试（那会把假的工作固化）。留着的理由是省掉 N 次 `git log`。
        only_left, unique = [], []
    elif right_is_ancestor:
        # 快路径（与上面的 `left_is_ancestor` 同性质，**也可以被删掉而不改变行为**）：
        # `right` 是 `left` 的祖先 ⇒ `left` 独有 `changed` 里的每个路径，
        # 走逐文件分支同样会把它们全判成独有（`right` 的历史里找不到这些新版本）。
        #
        # ⚠️ **只填 `unique`，绝不填 `superseded`**：这两个列表语义互斥 ——
        # 「独有」= `right` 从没见过该版本；「停在旧版」= `right` 历史里出现过该版本。
        # 同时填会让同一路径出现在报告的两处，**报告自相矛盾**（本仓 #123 时代
        # `list_side_only` 就踩过同型 bug）。有用例 `test_two_lists_are_disjoint` 钉着。
        only_left, unique = [], list(changed)
    else:
        # 互不包含：逐文件判「`left` 侧版本在 `right` 历史里出现过吗」。
        only_left, unique = [], []
        for path in changed:
            code_b, blob = _git(['rev-parse', '--verify', '--quiet', f'{left}:{path}'], cwd)
            if code_b != 0 or not blob:
                # 该路径在 `left` 上**不存在**（diff 的 deleted 侧）⇒ 谈不上「`left` 独有内容」。
                # 用 `--verify --quiet` 让「不存在」以退出码表达，而不是抛错。
                continue
            # ⚠️ 必须用 `--find-object=<blob>` 的**等号**写法：写成空格分隔的
            # `--find-object <blob>` 会被 git 当成 `--find-object` 不带值 + 一个多余的
            # revision 参数，实测直接退出 129（git 2.39.5）。这一处是踩出来的。
            hist = _git(['log', '--oneline', f'--find-object={blob}', right, '--', path], cwd)
            if hist[0] != 0:
                # 历史查询失败 ⇒ 判据不可用，**不得**默认成「出现过」。
                return {'available': False, 'reason': f'git log --find-object 退出码 {hist[0]}（路径 {path}）'}
            if hist[1]:
                # `left` 侧这个版本在 `right` 历史里存在 ⇒ `right` 曾经有过、`left` 停在旧版。
                only_left.append(path)
            else:
                unique.append(path)
    additions = deletions = 0
    if unique:
        code, out = _git(['diff', '--numstat', left, right, '--', *unique], cwd)
        if code != 0:
            return {'available': False, 'reason': f'git diff --numstat 退出码 {code}'}
        for line in out.splitlines():
            parts = line.split('\t')
            if len(parts) >= 3:
                additions += int(parts[0]) if parts[0].isdigit() else 0
                deletions += int(parts[1]) if parts[1].isdigit() else 0
    return {
        'available': True,
        'files': unique,          # **真正**是 left 独有的内容（判据只认这个）
        'superseded': only_left,  # left 停在旧版（right 曾经有过 ⇒ 正常滞后）
        'additions': additions,
        'deletions': deletions,
        'left_is_ancestor_of_right': left_is_ancestor,
        'right_is_ancestor_of_left': right_is_ancestor,
    }


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
        'content': content_ahead(left, right, cwd),
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
    """把结构化结果写成给人看的报告（CNB #179）。

    判据只有一条，但要说清三件事：
      1. **真分叉**：`left` 上有 `right` 拿不到的**内容**（逐文件判定，见 `content_ahead`）；
      2. **正常滞后**：`left` 停在旧版（那些文件 `right` 曾经有过）—— **不报红**；
      3. **判据不可用**：拿不到 git 结果 ⇒ 明说，**不得**退化成看起来正常的结论（#171）。

    为什么报告要写这么细：2026-10-14 之前，本判据把「`left` 停在旧版」也算成
    「`left` 有 `right` 没有的代码」，于是**每一次正常发版都留下一个永远红的信号**，
    而它不指向任何还需动手的事 —— 真违规反而被这层噪音淹掉（用户原话：
    「做了好多事情，但还是很乱」）。**报告的第一职责是别撒谎。**
    """
    left, right = res['left'], res['right']
    lo, ro = res['left_only'], res['right_only']
    content = res.get('content') or {}
    lines = [
        '## 分支分叉自检',
        '',
        f'- 比较：`{left}` ↔ `{right}`',
        f'- `{left}` 独有提交：**{lo}**',
        f'- `{right}` 独有提交：**{ro}**',
        '',
        f'### 内容级判据（`{left}` 有没有 `{right}` 拿不到的代码？）',
        '',
    ]

    if not content.get('available'):
        # 「拿不到」不是「没有」—— 必须显式说出，不得退化成看起来正常的结论（#171 教训）。
        lines.append(
            f'❓ **判据不可用**：{content.get("reason")}。'
            '本轮结论**不可信**，请先确认 git 可用后重跑。'
        )
        return '\n'.join(lines)

    unique = content.get('files') or []
    superseded = content.get('superseded') or []
    left_is_ancestor = bool(content.get('left_is_ancestor_of_right'))
    right_is_ancestor = bool(content.get('right_is_ancestor_of_left'))

    if unique:
        lines += [
            f'⚠️ **`{left}` 上有 `{right}` 拿不到的代码**（{len(unique)} 个文件，'
            f'+{content.get("additions")}/-{content.get("deletions")}）：',
            '',
        ]
        lines += [f'- `{f}`' for f in unique[:20]]
        if len(unique) > 20:
            lines.append(f'- …还有 {len(unique) - 20} 个，见 `git diff {left} {right}`')
        lines.append('')
    elif not superseded:
        lines.append(f'✅ **两侧内容一致**（`git diff {left} {right}` 为空）。')
        lines.append('')
    else:
        lines.append(
            f'✅ **`{left}` 没有 `{right}` 拿不到的代码**：'
            f'两侧有内容差异的 {len(superseded)} 个文件，`{left}` 上都是**旧版**'
            f'（该版本在 `{right}` 的历史里出现过 ⇒ `{right}` 已往前走了）。'
        )
        lines.append('')
        if len(superseded) <= 20:
            lines += [f'- `{f}`（`{left}` 停在旧版）' for f in superseded]
        lines.append('')

    lines += ['### 结构级信号（提交数，补充信息）', '']
    if not lo and not ro:
        lines.append('两侧一致。')
    elif lo and ro and not left_is_ancestor and not right_is_ancestor:
        lines.append(
            f'两侧**互不包含**（`{left}` 独有 {lo} / `{right}` 独有 {ro}）。'
            f'差异是「`{right}` 领先 + `{left}` 停在旧版」（见上）还是「`{left}` 被绕过」，'
            '以上面的内容级判据为准。'
        )
    elif lo:
        lines.append(f'`{left}` 独有 {lo} 个提交（发版节点属正常）。')
    else:
        lines.append(f'`{right}` 领先 `{left}` {ro} 个提交（待发版，属正常节奏）。')
    lines.append('')

    for side, jobs in (
        (left, res['left_only_jobs']),
        (right, res['right_only_jobs']),
    ):
        if jobs:
            lines.append(f'**只在 `{side}` 上的作业配置**（改了不跑 / 跑了不是它）：')
            lines.append('')
            lines.extend(f'- `{p}`' for p in jobs)
            lines.append('')

    lines += [
        '> 处置：**发版**（`dev` → `main` 的 PR，head 必须是 `dev` 本身）。',
        '> 不要用「把功能分支 base 改成 main」消除时间差 —— 那正是本分叉的成因（见 AGENTS.md「PR 与 Review」）。',
        '> 若发版后**仍**红，说明有提交没经过 `dev` 就落在 `main` 上了 —— 那时才是纪律问题。',
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
    # 退出码口径（CNB #167）：**内容级**才算分叉 —— `left` 有 `right` 拿不到的代码。
    # 发版 merge commit（内容 diff 为空）不算；判据不可用时返回 2（与「取不到分支」同语义），
    # 绝不放行成 0（「拿不到 ≠ 正常」，#171 教训）。
    content = res.get('content') or {}
    if not content.get('available'):
        diverged = None
    else:
        # 只看 `files`（逐文件判定后的**真独有**）。`superseded` 是「left 停在旧版」，
        # 属正常滞后 ⇒ 不计入。旧版在这里用「`git diff` 非空」判红，把滞后也算成独有，
        # 于是每次正常发版都红一次（#179 要消灭的假红）。
        diverged = bool(content.get('files'))
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
    if diverged is None:
        return 2  # 判据不可用：不得当作「正常」
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

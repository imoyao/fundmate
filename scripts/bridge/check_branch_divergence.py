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

判据（二分，源 CNB #179，2026-10-14）
--------------------------------------
初版的「`main` 独有提交数 > 0 ⇒ 分叉」在本仓**恒为真**：`dev` 发完版继续走，
`main` 必然既不领先、也不是 `dev` 的祖先 ⇒ **每次发版都报红**，而红的是合规发版本身。
「喊狼来了」喊多了，红灯就不再被人当真 —— 这比没有自检更坏。

现在**两层判据，任一层成立才红**：

1. **提交级**（逐笔二分，`classify_unique_commits()`）：
   - `left` 独有提交是 merge、且其**第二父**是 `right` 的祖先 ⇒ `release`，**不红**；
   - 是普通提交，或 merge 的第二父不是 `right` 的祖先 ⇒ `violation`，**红**；
   - 提交读不出来 ⇒ `unknown`，**也红**（「拿不到输入」不得退化成「正常」）。
2. **内容级**（`content_ahead()`，`git cherry` 补丁等价）：`left` 上有 `right` 拿不到的
   改动 ⇒ 红。这一层兜住「有人绕过 `right` 在 `left` 上改了文件」。

`right` 领先 `left`（待发版量）**不红** —— 那是本仓的正常态。

### 判据选型的实测教训（#179）

`git diff <left> <right>` 非空 **不等于**「`left` 有独有内容」。本仓交叉合并
（`main` 合过 `dev@c76b7621`、`dev` 又往前走了）后，两侧**都不是对方的祖先**，
diff 也非空 ⇒ 旧版报「`main` 有 7 个文件 `dev` 没有」。**实测这 7 个全假**：
`git cherry <right> <left>` 为空，`left` 一个字节的独有内容都没有。故内容级改用
`git cherry`（一个判据直接回答被问的问题），不再拼「diff + 祖先关系」那条两步路。

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
- **退出码**：0 = 无新形态；1 = 有新形态（供 CI 当信号用）；2 = 取不到 `left` / `right`
  （「分支不存在」与「判出问题」是两件事，混在一起就分不出是哪一种）。调用方若不想要红灯，
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
    """**内容级**判据：`left` 有没有 `right` 拿不到的**代码**（源 CNB #167 → #179 修正）。

    为什么不能只看提交数：发版 PR（`right` → `left`）**必然**给 `left` 留一个 merge commit，
    而它**不引入任何内容**。旧版 `count_unique(left) > 0` 把这种**正常的发版节点**
    也报成「已分叉」，每发一次版就红一次——红却不指向任何还需动手的事，是**假红**
    （与 #118 的假绿同族）。

    ### #179 实测踩到的坑：`git diff` **不是**这个判据

    上一版用「`git diff <left> <right>` 非空 ⇒ `left` 有独有内容」。它在**交叉合并**后失灵：

        `main` 合过 `dev@c76b7621`，`dev` 又往前走了 2 个提交 ⇒
        **两侧都不是对方的祖先**（`--is-ancestor` 双向皆 false），
        于是 `left_is_ancestor_of_right=False` 且 diff 非空 ⇒ 报 ⚠️「main 有 7 个文件 dev 没有」。

    **实测这 7 个文件全是假阳性**：`git cherry <right> <left>` 为空 ——
    `left` 上**每一条提交都能在 `right` 找到补丁等价的对应**，
    `left` 一个字节的独有内容都没有。diff 非空只是因为 `right` **更靠前**（领先 2 个提交），
    而「更靠前」在交叉合并下**不能**由「非祖先」推出来。

    故判据换成 **`git cherry`（补丁等价）**，它才是「`left` 有没有 `right` 没有的改动」的正解：

        git cherry <right> <left>   # 逐行输出 `+ <sha>`（right 缺）/ `- <sha>`（right 已有等价）

      - **没有 `+` 行** ⇒ `left` 的改动 `right` 全有 ⇒ 不算分叉（放行发版滞后）；
      - **有 `+` 行** ⇒ `left` 上有 `right` 拿不到的改动 ⇒ 这才是要拦的形态。

    为什么不用 `diff` + 祖先关系拼：那条路要**两个判据同时成立**才敢放行，
    而交叉合并恰好卡在中间（都 false / 都非空）。`git cherry` 是一个判据、
    直接回答被问的那个问题。

    ### 另一个曾考虑的判据：逐文件 blob 历史（`git log --find-object`）——也不可用

    PR #181 冲突复盘时的实测：另一版实现遍历 `git diff --name-only` 的每个路径，
    再问「`left` 侧那个 blob 在 `right` 历史里出现过吗」。它**同样在交叉合并下漏报真违规**：

        `main` 合过 `dev` 后**删掉**了一个文件、`dev` 再往前走 ⇒
        `git diff --name-only` 里那个文件是**删除侧**（`left:{path}` 解析失败），
        实现把它 `continue` 跳过 ⇒ 判定「✅ 两侧内容一致」**假绿**，
        而 `git cherry <right> <left>` 明确报 `+`（真违规）。

    根因是判据的**取值域**被 `git diff` 的输出侧限定住了（只看 `left` 侧存在的路径），
    删除类改动天然落在域外。`git cherry` 以**补丁**为单位，没有这个盲区，
    故内容级一律用它 —— 这也是「拿不到输入（该路径在 left 不存在）不得退化成正常」的落实。

    取不到 git 结果时返回 `available=False` 表示**判据不可用**——**不猜、不降级成「正常」**
    （否则又是「拿不到输入 = 输入为空」，见 #171）。
    """
    code, out = _git(['cherry', right, left], cwd)
    if code != 0:
        return {'available': False, 'reason': f'git cherry 退出码 {code}'}
    only_left: list[str] = []
    for line in out.splitlines():
        line = line.rstrip()
        # 形如 `+ <sha>`（right 缺这条改动）或 `- <sha>`（right 已有等价补丁）。
        # 只认 `+`；`-` 正是「右侧已有等价改动」的**放行**信号。
        if line.startswith('+'):
            sha = line[1:].strip()
            if sha:
                only_left.append(sha)
    # 与「哪些文件」一并给出：光说「有 3 条独有提交」不够，读者要知道碰了哪些路径。
    # 逐个 `git show --name-only` 而不是一条 `git log -- <rev^!...>`：前者对每个 sha
    # 独立取变更路径，不受 pathspec 括号展开形态（Windows / 不同 git 版本差异）影响，
    # 也不会被 `--pretty=format:` 的空行吃掉（实测 `log --name-only --pretty=format:` 会给出空）。
    files: list[str] = []
    for sha in only_left:
        code, names = _git(['show', '--name-only', '--format=', sha], cwd)
        if code == 0:
            files.extend(ln.strip() for ln in names.splitlines() if ln.strip())
    return {
        'available': True,
        'has_only_left': bool(only_left),
        'only_left_commits': only_left,
        'files': files,
    }


def parse_commit(sha: str, cwd: str | None = None) -> dict | None:
    """把一个提交读成 `{sha, short, subject, parents}`；**取不到返回 None，不猜**。

    `git log -1 --format=%h%x09%s%x09%P <sha>`：`%h` 短号、`%s` 主题、
    `%P` **全部**父提交（merge 有两个，空格分隔）。用 TAB 分隔是因为主题里
    可能含任意字符、含空格是常态。
    """
    code, out = _git(['log', '-1', '--format=%h%x09%s%x09%P', sha], cwd)
    if code != 0 or not out:
        return None
    parts = out.splitlines()[0].split('\t')
    if len(parts) < 3:
        return None
    return {
        'sha': sha,
        'short': parts[0],
        'subject': parts[1],
        'parents': [p for p in parts[2].split() if p],
    }


def classify_commit(commit: dict, right: str, cwd: str | None = None) -> dict:
    """判断 `left` 上的一个独有提交是「合规发版」还是「纪律违规」（源 CNB #179）。

    - **普通提交**（父 < 2）⇒ `violation`：它没有「被合进来」的语义，
      在稳定分支上只能意味着有人绕过 `right` 直接提交 / 直接推；
    - **合并提交** ⇒ 看**第二父**是不是 `right` 的祖先：
        - 是 ⇒ `release`（合规发版：把 `right` 合进 `left`）；
        - 否 ⇒ `violation`（合并的另一侧来路不明，等于绕过了 `right`）。

    ⚠️ **是第二父，不是第一父**：`git log --format=%P` 的**第一父**是当前分支自己的历史
    （`left` 上继续的那个），**第二父**才是被合入的一侧。取第一父判「是不是 `right` 的祖先」，
    会把每一笔合规发版都判成违规 —— 「判据方向错等于报告不可用」。

    父提交信息**取不到**时返回 `unknown`：拿不到输入不得退化成「正常」（假绿），
    也不得退化成「违规」（替人定罪）—— 两种都是替人做判断。
    """
    parents = commit.get('parents') or []
    if len(parents) < 2:
        return {'kind': 'violation', 'reason': f'普通提交（非合并）出现在稳定分支上：无人经 `{right}` 中转'}
    merged_side = parents[1]
    code, _ = _git(['merge-base', '--is-ancestor', merged_side, right], cwd)
    if code == 0:
        return {
            'kind': 'release',
            'merged_side': merged_side[:8],
            'reason': f'合规发版：合并的第二父 {merged_side[:8]} 是 `{right}` 的祖先',
        }
    if code == 1:
        return {
            'kind': 'violation',
            'merged_side': merged_side[:8],
            'reason': f'合并的第二父 {merged_side[:8]} 不是 `{right}` 的祖先：来路不明',
        }
    return {
        'kind': 'unknown',
        'reason': f'取不到 {merged_side[:8]} 与 `{right}` 的祖先关系（git 退出码 {code}）',
    }


def classify_unique_commits(left: str, right: str, cwd: str | None = None) -> dict:
    """把 `left` 独有的提交逐个分类（源 CNB #179）。

    返回 `{commits, violations, unknowns, commits_readable}`：
      - `commits` = 全部独有提交，每条带 `verdict`（`release` / `violation` / `unknown`）；
      - `violations` / `unknowns` = 该报红的两类；
      - `commits_readable` = 提交清单**取得**到吗（False ⇒ 判据不可用，不得读成「无异常」）。
        键名与 `needs_red()` / `build_report()` 的读取点一致（合并时修正了
        写 `readable` 读 `commits_readable` 的错位——测试手工构 dict 绕过了管道，
        #171「拿不到 ≠ 没有」在真实 compute() 里曾是死路径）。
    """
    code, out = _git(['log', '--format=%H', f'{right}..{left}'], cwd)
    if code != 0:
        return {'commits': [], 'violations': [], 'unknowns': [], 'commits_readable': False}
    commits: list[dict] = []
    for sha in [ln.strip() for ln in out.splitlines() if ln.strip()]:
        commit = parse_commit(sha, cwd)
        if commit is None:
            commits.append(
                {
                    'sha': sha,
                    'short': sha[:8],
                    'subject': '<读取失败>',
                    'verdict': {'kind': 'unknown', 'reason': '取不到提交信息'},
                }
            )
            continue
        commit['verdict'] = classify_commit(commit, right, cwd)
        commits.append(commit)
    return {
        'commits': commits,
        'violations': [c for c in commits if c['verdict']['kind'] == 'violation'],
        'unknowns': [c for c in commits if c['verdict']['kind'] == 'unknown'],
        'commits_readable': True,
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
        **classify_unique_commits(left, right, cwd),
    }


def needs_red(res: dict) -> bool:
    """该不该报红 —— **只看有没有新形态**，不看「分叉了几个提交」（源 CNB #179）。

    两层判据，任一层成立就红：

      - **提交级**：`left` 独有提交里有 `violation`（普通提交 / 来路不明的 merge）
        或 `unknown`（判不出）⇒ 红。`release`（合规发版 merge）**不红**；
      - **内容级**（`content_ahead()`，源 #167）：`left` 有 `right` 拿不到的**代码** ⇒ 红。
        发版 merge 不引入内容，故正常情况下两层口径一致；内容级兜住「有人绕过 `right`
        在 `left` 上改了文件」这类形态。

    两个「拿不到输入」都**不得**退化成正常：`commits_readable` 为假、或
    `content.available` 为假 ⇒ 红（#171 那条「拿不到 ≠ 空的」）。
    """
    if res.get('commits_readable') is False:
        return True
    if res.get('violations') or res.get('unknowns'):
        return True
    content = res.get('content') or {}
    if not content.get('available'):
        return True
    return bool(content.get('has_only_left'))


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
    """报告分三段：**提交级二分**（该不该红）→ **内容级**（#167 口径）→ **结构级**（补充）。

    为什么提交级放最前：判据二分之后，「该不该红」由它回答；内容级与结构级都是**佐证**，
    其中内容级**仍有独立价值**——它兜住「有人在 `left` 上改了文件、`right` 拿不到」这类
    形态（那种情况下提交级也会红，但内容级能直接点名文件）。
    """
    left, right = res['left'], res['right']
    lo, ro = res['left_only'], res['right_only']
    commits = res.get('commits') or []
    violations = res.get('violations') or []
    unknowns = res.get('unknowns') or []
    releases = [c for c in commits if (c.get('verdict') or {}).get('kind') == 'release']
    content = res.get('content') or {}

    lines = [
        '## 分支分叉自检',
        '',
        f'- 比较：`{left}` ↔ `{right}`',
        f'- `{left}` 独有提交：**{lo}**（合规发版 {len(releases)} / 新形态 {len(violations)} / 判不出 {len(unknowns)}）',
        f'- `{right}` 独有提交：**{ro}**（待发版量，正常态）',
        '',
        '### 提交级判据（逐笔二分：合规发版 / 新形态）',
        '',
    ]

    if res.get('commits_readable') is False:
        # 「拿不到输入」≠「输入为空」：显式说出并以红灯表达（#171 / #179）。
        lines.append(
            f'❌ **判据不可用**：取不到 `{left}` 独有的提交清单（`git log` 失败）。'
            '本轮**无法给出结论**，不得读成「无异常」；先确认 git 可用、ref 存在后重跑。'
        )
    elif violations:
        lines.append(f'⚠️ **检出 {len(violations)} 个新形态** —— `{left}` 上有未经 `{right}` 中转的提交：')
        lines.append('')
        for c in violations:
            lines.append(f'- `{c["short"]}` {c["subject"]} —— {(c.get("verdict") or {}).get("reason", "")}')
        lines.append('')
        lines.append(f'处置：查清来路，走 PR 把它并回 `{right}`（**不要**用 `--force` 抹掉）。')
    elif releases:
        lines.append(
            f'✅ 无新形态：`{left}` 独有的 {len(releases)} 个提交**全部是合规发版 merge**'
            f'（把 `{right}` 合进 `{left}`）。'
        )
        lines.append('')
        lines.append(
            f'这是本仓的正常态 —— `{right}` 领先 {ro} 个提交，`{left}` 停在上一发版点。'
            '**不要拿它当红灯**：为了消红而强行对齐只会逼出下策。'
        )
    else:
        lines.append(f'`{left}` 没有独有提交。')

    if unknowns:
        lines += [
            '',
            f'❓ **{len(unknowns)} 个提交判不出类型**（拿不到父提交 / 祖先关系）——**按红灯对待**：',
        ]
        lines.extend(f'- `{c["short"]}` {c["subject"]}' for c in unknowns)

    # ---- 内容级（#167 口径，用 git cherry 补丁等价判定） ----
    lines += ['', '### 内容级判据（口径：`' + left + '` 不得有 `' + right + '` 拿不到的代码）', '']
    if not content.get('available'):
        lines.append(f'❓ **判据不可用**：{content.get("reason")}。「拿不到」不是「没有」——**不得读成本轮无异常**。')
    elif content.get('has_only_left'):
        only = content.get('only_left_commits') or []
        files = content.get('files') or []
        lines += [
            f'⚠️ **`{left}` 上有 {len(only)} 条 `{right}` 拿不到的改动**' + f'（`git cherry {right} {left}` 报 `+`）：',
            '',
        ]
        lines += [f'- `{s[:8]}`' for s in only[:20]]
        if files:
            lines += ['', '涉及路径：', '']
            lines += [f'- `{f}`' for f in files[:20]]
        lines.append('')
    else:
        lines.append(
            f'✅ **`{left}` 没有 `{right}` 拿不到的改动**'
            f'（`git cherry {right} {left}` 无 `+` 行：`{left}` 上每条提交都在 `{right}` 有补丁等价的对应）。'
        )
        # 绿灯要说清**是哪一种绿灯**：`left` 停在旧版（`right` 领先）是正常滞后，
        # 与「两侧完全一致」不是一回事。少了这句，读者看到绿也答不出「那我还要不要发版」。
        # 判据本身只认 `git cherry`；这里**只做措辞**，不引入第二个判据（避免又拼出假红/假绿）。
        if lo and ro:
            lines.append(
                f'`{left}` 停在上一发版点、`{right}` 领先 {ro} 个提交 —— 这是正常滞后，'
                f'**不是**「`{left}` 有独有内容」。'
            )

    # ---- 结构级（提交数，补充） ----
    lines += ['', '### 结构级信号（提交数，补充信息）', '']
    if not lo and not ro:
        lines.append('两侧一致。')
        return '\n'.join(lines)
    lines.append(f'`{left}` 独有 {lo} / `{right}` 独有 {ro}。')
    lines.append('')
    lines.append('> ⚠️ 提交数**不是判据**：交叉合并（`main` 合过 `dev`、`dev` 又前进）下')
    lines.append('> 两侧会「互不包含」而 `left` 其实零独有内容 —— 这正是 #179 实测的假阳性形态。')

    for side, jobs in ((left, res['left_only_jobs']), (right, res['right_only_jobs'])):
        if jobs:
            lines += ['', f'**只在 `{side}` 上的作业配置**（改了不跑 / 跑了不是它）：', '']
            lines.extend(f'- `{p}`' for p in jobs)

    lines += [
        '',
        '> 判据口径（源 CNB #179）：**合规发版 merge 不报红**（`' + left + '` 停在上一发版点是正常态）；',
        f'> `{left}` 独有普通提交、或合并的第二父不是 `{right}` 的祖先，才是**新形态**。',
        '> 只报告，不改动：不 fetch / merge / push（要不要更新远端视图是调用方的决定）。',
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
    # 退出码口径（源 CNB #179）：**有没有新形态**，不是「left 独有提交数是不是 0」。
    # 合规发版滞后在本仓恒存在（`dev` 一直在前进），拿它当红灯就是「狼来了」——
    # 判定交给 `needs_red()`，它同时覆盖提交级二分与 #167 的内容级判据。
    diverged = needs_red(res)
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

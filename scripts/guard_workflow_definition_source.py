#!/usr/bin/env python3
"""workflow 定义来源守卫（#2803）。

## WHY：这条守卫守的是「改了 workflow，但那条路径跑的还是旧定义」

GitHub 于 2025-12-08 生效的行为变更（官方 changelog「Actions pull_request_target and
environment branch protections changes」）原文：

> The pull_request_target event now always uses the default branch for workflow source
> and reference: The workflow file and checkout commit will always be taken from the
> repository's default branch, regardless of the pull request's base branch.

配套文档「Securely using pull_request_target」也写明：*"the workflow, and any subsequent
actions/checkout call that does not specify a ref, is taken from the base repository's
default branch"*。

本仓默认分支是 `main`，而功能 PR 一律 base=`dev`，`main` 落后 `dev` 数百个提交
⇒ 走 `pull_request_target` 的那条路径，**跑的是 `main` 上那份定义**。于是：

- 在 dev 上把 token 换成 PAT —— `main` 上那份还写着 `secrets.GITHUB_TOKEN`，**改了不起作用**；
- 在 dev 上加守卫、改判据、调 cron —— 同理，**全部不可见**。

2026-11-01 实测（本仓 PR #2801，base=dev 且 dev 上已含新版定义，且 dev tip 早在
08:58 就已合入、探针 run 09:08 才触发，晚了整整 10 分钟）：新版那行
`启用 auto-merge 的凭据身份：$actor` 的 echo **没有出现在日志里**，取而代之的是
`main` 旧版逐字一致的文案 ⇒ 实证「定义来自默认分支」，而非 base 分支。

**这类故障没有任何报错**：CI 照常绿、PR 照常合得进去，只有行为不一致。
本守卫把它变成**可判红的静态判据**。

## 判据（任一不满足即红，并入 ci.yml 的 scripts_test，阻断）

1. **仓库内不得存在 `pull_request_target` 触发器**——**除显式登记的豁免项**
   （`_PRT_EXEMPT`，当前是那两个由依赖 bot 触发的工作流，理由见常量处的注释）。
   它的定义永远锁在默认分支上 ⇒ dev 上的改动对这条路径不可见。
   `pull_request` 的定义取自 PR 的 merge commit（dev tip + PR head）⇒ 立刻生效。
   同仓分支的 `pull_request` 与 `pull_request_target` 权限一致（官方文档：
   *"The same is true for workflows triggered on pull_request from a branch in the same
   repository, but not from external forks."*）⇒ 本仓（功能分支全在仓内）不损失能力。

   **豁免不是随意的**：`_PRT_EXEMPT` 里的每个条目都要写清「为什么这个工作流
   离不开 `pull_request_target`」，且必须在 `_GUARD_WORKFLOWS` 清单里（这样它的
   checkout 仍受判据 2 约束）。豁免项若被迁走，守卫会要求把豁免删掉——
   否则清单会变成藏污纳垢的地方，而「豁免已失效」这件事本身没人会注意到。

2. **「从 `pull_request_target` 迁过来的」工作流，其 checkout 必须显式写 `ref: dev`。**
   这类工作流**执行仓库里的守卫脚本**（`scripts/guard_*.mjs` / `claim_in_progress.mjs` 等），
   而：
   - `pull_request_target` 下 checkout 默认检出 **base 分支**（受信）；
   - `pull_request` 下默认检出 **merge commit（含 PR 代码）**。
   ⇒ 迁移时不补 `ref`，等于给 PR 作者一个「改掉自己的守卫」的入口
   （把 `guard_pr_four_questions.mjs` 的判据改成恒真、把 `GOV_GLOB` 改空）。
   显式写 `ref: dev` 才是「执行内容始终受信」的写法。

   **判据只管这一类，不管 CI**：`ci.yml` / `docker-build.yml` / `ai-review.yml` 这些
   **本来就要检出 PR 代码**——CI 的职责就是测 PR 的代码，要求它们写 `ref: dev`
   反而会让 CI 测错东西（测的是 dev 而不是 PR）。
   ⇒ 本判据用**显式清单**列出「执行守卫脚本的工作流」，而不是靠猜。

3. **不得把 `pull_request_target` 藏在注释或字符串里**——注释里提到不算触发器
   （本仓判据被自己的说明文字咬过多次）。

4. **迁到 `pull_request` 的工作流，其 `concurrency.group` 必须带一个**过渡期后缀**
   （本仓约定：group 名含 `-pr-`），使其与**默认分支上的旧版定义**算出的 group 名
   **不同**。

   理由：过渡期内 `main` 上的旧版（`pull_request_target`）与 `dev` 上的新版
   （`pull_request`）**会同时被触发**。若两者 group 名相同 ⇒
   **`cancel-in-progress: true` 的一方会把另一方取消**——而且是**发起取消的那一方**
   取消掉对方（实测：旧版 success、新版 cancelled）。
   ⇒ **守卫被静默取消**，而 GitHub 把 cancelled 记成 check 失败（显示 fail）。

   ⚠️ **只把新版改成 `cancel-in-progress: false` 是不够的**——取消是旧版发起的，
   新版无论自己是什么设置都会被取消掉（2026-11-01 实测：改了 `false` 之后
   新版仍被 cancelled）。**必须让两者的 group 名不同**。

   判据盯的是**group 名是否与旧版撞车**，不是 `cancel-in-progress` 的取值：
   撞车了才需要后缀；不撞车时 `cancel-in-progress: true` 是正常的去重语义。

   后缀在发版后自然失效：`main` 上的旧版被替换成新版 ⇒ 两边 group 名一致 ⇒
   恢复单一序列。故这个后缀**不需要**在发版后回改。

   **本仓 `main` 旧版的实际形态**（2026-11-01 逐个核过）：

   | 工作流 | `main` 旧版 | 故障形态 |
   |---|---|---|
   | `pr-four-questions-guard` | group `pr-four-questions-guard-<n>`，`cancel-in-progress: true` | **会取消新版**（实测命中） |
   | `issue-claim-sync`        | group `claim-in-progress-<n>`，`cancel-in-progress: false` | 不取消，但同组排队 |
   | `pr-overlap-guard`        | **无 concurrency** | 无互斥；新旧各跑一次 ⇒ 可能重复评论 |
   | `pr-auto-rebase`          | **无 concurrency** | 无互斥；新旧各跑一次 ⇒ 可能重复 force-push |
   | `pr-auto-merge`           | **无 concurrency** | 无互斥；新旧各跑一次 ⇒ 可能重复尝试合并 |

   ⚠️ **旧版没有 group 的那三个，不靠 group 名解决**：后缀只能分开新版彼此，
   不能让旧版消失 ⇒ 过渡期它们必然新旧各跑一次，副作用会重复。这只能靠
   「`main` 被新版替换」自然消失（发版后即不再发生），已作为「过渡期已知残留」
   记在 `#2803` 的进展评论里。

   而**声明了 group 的两个，跑两次都无害**（所以可以让新旧并存、各跑各的）：
   `pr-four-questions-guard` 只读正文 + 返回退出码；`issue-claim-sync` 打/摘标签
   （幂等）+ 撞车告警评论（隐藏键幂等，见 `scripts/claim_in_progress.mjs`）。

## 边界（刻意不查）

- **不查 `schedule` 事件的定义来源**：`schedule` **没有**除默认分支以外的定义来源
  选项（这是平台行为，改不了）⇒ 它的漂移只能靠「`main` 与 `dev` 同步」解决，
  而本仓的 `dev → main` 发版 PR 本来就干这件事。
  它的**执行内容**已由既有守卫 `scripts/guard_schedule_checkout_ref.py` 治理
  （强制显式 `ref` 且不得是默认分支），不在本守卫范围。
- **不查 `push` 事件的定义来源**：`push` 的定义来源是**被推的分支**（= `dev`），
  本来就是新的。
- **不查默认分支本身该不该是 `main`**：本仓 `main` 是发版通道的锚点（tag 打在
  `origin/main` 上），改默认分支是更大的决策，不在本守卫范围。
- **不查 checkout 的 ref 到底解析成什么**：`ref: ${{ env.X }}` 这类表达式放行
  ——静态判据不该猜运行时取值（同 `guard_schedule_checkout_ref.py` 的口径）。
- **不查 CI 类工作流的 checkout**（`ci.yml` / `docker-build.yml` / `ai-review.yml`）：
  它们检出 PR 代码是**职责所在**，不是缺陷。
- **不查 `governance-direction-guard.yml`**：它检出 PR 代码并执行 PR 里的
  `scripts/governance_files_rule.js`，形式上与判据 2 同类。但它在本次迁移**之前**
  就是 `pull_request`（不是从 `pull_request_target` 迁来的），属既有形态，
  不在本次范围（另记 issue 跟进）。

## 用法

    python scripts/guard_workflow_definition_source.py            # 校验（CI）
    python scripts/guard_workflow_definition_source.py --report   # 打印通过项

退出码：0 = 通过；1 = 命中栅栏；2 = 拿不到输入（结论不可信，**不得**当成通过）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

WORKFLOW_DIR = '.github/workflows'

# 默认分支的几种写法（显式写它们 = 检出「默认分支上那份旧定义/旧代码」）。
_DEFAULT_BRANCH = {'main', 'master', 'refs/heads/main', 'refs/heads/master'}

# 判定「这个 ref 指向 PR 自己的分支」的几种写法。
# 这些一旦出现，就等于把 checkout 交回给了 PR 作者。
_PR_HEAD_PATTERNS = (
    'github.event.pull_request.head.ref',
    'github.head_ref',
)

# 「执行仓库内守卫脚本」的工作流清单（判据 2 的适用范围）。
#
# 为什么用显式清单而不是靠猜「有没有跑 scripts/」：
#   - `ci.yml` / `docker-build.yml` / `ai-review.yml` **本来就该检出 PR 代码**
#     ——CI 的职责就是测 PR 的代码，要求它们写 `ref: dev` 反而让 CI 测错东西；
#   - 但 `pr-four-questions-guard.yml` 这类**守卫**工作流执行的是仓库里的
#     `scripts/guard_*.mjs`，检出 PR 代码 = PR 作者能改掉自己的守卫。
# 两者形式上都是「pull_request + checkout 无 ref」，只能靠「职责」区分，不能靠形态。
#
# 清单里每个名字对应一条本仓已知的迁移（#2803：6 个工作流从 `pull_request_target`
# 迁到 `pull_request`，迁移时必须补 `ref: dev`）。
_GUARD_WORKFLOWS = {
    'dependabot-auto-merge.yml',        # 不 checkout（只用 gh API）⇒ 无需 ref
    'dependabot-lockfile-regen.yml',    # 已显式 ref: dev
    'issue-claim-sync.yml',             # 已显式 ref: dev
    'pr-auto-rebase.yml',               # 已显式 ref: dev
    'pr-four-questions-guard.yml',      # 已显式 ref: dev
    'pr-overlap-guard.yml',             # 已显式 ref: dev
    'pr-auto-merge.yml',                # 不 checkout（只用 gh API）⇒ 无需 ref
}

# 「合法保留 `pull_request_target`」的工作流清单（判据 1 的豁免）。
#
# 为什么要豁免而不是一刀切禁止：`pull_request_target` 不是无用的事件，它有一个
# **正当且不可替代**的用途——**给依赖 bot 触发的 PR 提供写权限**。
# GitHub 官方文档原文：
#
# > Workflows triggered by Dependabot pull requests are treated as though they are
# > from a forked repository, and are also subject to these restrictions.
# > The GITHUB_TOKEN has read-only permissions in pull requests from forked repositories.
#
# ⇒ Dependabot 的 PR 即使 head 仓库就是本仓，在 `pull_request` 事件下 token 仍是
# **只读**、secrets 也不注入 ⇒ 这类工作流里的 `git push` / `gh pr merge --auto`
# **必然失败**（`#578` 同族事故）。
#
# 「head 仓库相同」≠「权限相同」——dependabot 被平台特殊对待。这两个工作流就是
# 依赖 bot 触发的（`dependabot-auto-merge` 要合并依赖 PR、`dependabot-lockfile-regen`
# 要把重生成的锁推回 dependabot 分支）⇒ 只能留在 `pull_request_target`。
#
# 代价（明确接受）：它们的定义仍锁在默认分支 `main` 上，dev 上的改动要等发版才生效。
# 处置见 `#2803`。
_PRT_EXEMPT = {
    'dependabot-auto-merge.yml': '依赖 bot 触发 ⇒ pull_request 下 token 只读，gh pr merge 必然失败',
    'dependabot-lockfile-regen.yml': '依赖 bot 触发 ⇒ pull_request 下 token 只读，git push 必然失败',
}

# 判据 4 的适用范围：**迁移到 `pull_request`、且声明了 `concurrency.group`** 的工作流。
#
# 判据要防的具体故障是：**默认分支上的旧版（`pull_request_target`）与 dev 上的
# 新版（`pull_request`）算出了同一个 concurrency group** ⇒ 同组内
# `cancel-in-progress: true` 的一方会把另一方取消（实测 PR #2807：
# 旧版 success、新版 cancelled）⇒ 新版那条挂在 PR head 上的 check 被取消
# ⇒ GitHub 把 cancelled 记成 check 失败 ⇒ PR 假红。
#
# 逐个核过 main 上旧版的 concurrency（2026-11-01）：
#
# | 工作流 | main 旧版 | 故障形态 |
# |---|---|---|
# | `pr-four-questions-guard` | group `pr-four-questions-guard-<n>`，`cancel-in-progress: true` | **会取消新版**（实测命中） |
# | `issue-claim-sync`        | group `claim-in-progress-<n>`，`cancel-in-progress: false` | 不取消，但同组排队 |
# | `pr-overlap-guard`        | **无 concurrency** | 无互斥；但新旧各跑一次 ⇒ 可能重复评论 |
# | `pr-auto-rebase`          | **无 concurrency** | 无互斥；但新旧各跑一次 ⇒ 可能重复 force-push |
# | `pr-auto-merge`           | **无 concurrency** | 无互斥；但新旧各跑一次 ⇒ 可能重复尝试合并 |
#
# ⚠️ **旧版没有 group 的那三个，不靠 group 名解决**：后缀只能分开新版彼此，
#    不能让旧版消失 ⇒ 过渡期它们必然新旧各跑一次，副作用会重复。
#    这只能靠「`main` 被新版替换」自然消失（发版后即不再发生），
#    已作为「过渡期已知残留」记在 `#2803` 的进展评论里。
#
# 而**声明了 group 的两个，跑两次都无害**（所以可以让新旧并存、各跑各的）：
#   - `pr-four-questions-guard`：只读 PR 正文 + 返回退出码（不评论、不写标签）；
#   - `issue-claim-sync`：打/摘标签（幂等）+ 撞车告警评论（隐藏键幂等，
#     见 `scripts/claim_in_progress.mjs` 的 `COLLISION_HIDDEN_MARK`）。
#
# 过渡期后缀的约定：group 名里必须出现它。
# 为什么用固定约定而不是「与默认分支旧版比对」——后者要拉网络、拿默认分支的旧文件，
# 静态判据做不了（CI 里也不该为此调 API）。约定成固定后缀后，
# 「新旧两组并存、发版后自然合一」的性质由后缀语义保证。
_TRANSITION_SUFFIX = '-pr-'

# 「允许与默认分支旧版共用同一个 group 名」的工作流豁免。
# 留空 = 本仓当前没有这类工作流。
# 若将来有（例如某个工作流跑了两次会有不可接受的副作用、宁可让新版被取消），
# 必须在这里登记并写清理由——否则守卫默认「后缀无害」而放行。
_SAME_GROUP_EXEMPT: Dict[str, str] = {}


def _import_yaml():
    try:
        import yaml
    except ImportError:  # pragma: no cover - CI 里由 setup-python + pip 提供
        raise SystemExit('缺少 pyyaml：本判据依赖 YAML 解析（ci.yml 的 scripts_test 已安装）')
    return yaml


def _triggers(doc: Dict[str, Any]) -> Dict[str, Any]:
    """取 `on:` 的字典形态。

    YAML 1.1 把裸 `on` 解析成布尔 True，所以 `doc.get('on')` 常拿到 None——
    必须同时试 `doc[True]`。这个坑本仓判据踩过。
    """
    raw = doc.get('on')
    if raw is None:
        raw = doc.get(True)
    return raw if isinstance(raw, dict) else {}


def _strip_comments(text: str) -> str:
    """去掉整行注释（`#` 开头）与行尾注释。

    为什么要去注释：判据若直接在原文里搜 `pull_request_target`，那么
    「文件头解释『为什么不用 pull_request_target』的那段说明」会被当成命中
    ——本仓判据被自己的说明文字咬过多次（`guard_schedule_checkout_ref.py` 记在案）。
    """
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        # 行尾注释：不在引号内的 # 之后才算注释。
        in_single = in_double = False
        cut = None
        for i, ch in enumerate(line):
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == '#' and not in_single and not in_double:
                if i == 0 or line[i - 1] in ' \t':
                    cut = i
                    break
        out.append(line if cut is None else line[:cut])
    return '\n'.join(out)


def _checkout_refs(job: Dict[str, Any]) -> List[Tuple[str, str]]:
    """取一个 job 里所有 checkout step 的 (step 名, ref 值)。

    没有 `with.ref` 时返回空串——**空串本身就是判据 2 要抓的形态**
    （`pull_request` 下会检出 merge commit）。
    """
    refs: List[Tuple[str, str]] = []
    for step in job.get('steps') or []:
        if not isinstance(step, dict):
            continue
        if 'actions/checkout' not in str(step.get('uses', '')):
            continue
        with_ = step.get('with') or {}
        ref = (with_.get('ref') or '') if isinstance(with_, dict) else ''
        refs.append((str(step.get('name') or step.get('uses') or 'checkout'), str(ref).strip()))
    return refs


def check(repo: Path) -> List[str]:
    """返回问题清单；空列表 = 通过。"""
    problems: List[str] = []
    yaml = _import_yaml()

    wf_dir = repo / WORKFLOW_DIR
    if not wf_dir.is_dir():
        return [f'找不到 {WORKFLOW_DIR}/ 目录 —— 结论不可信']

    files = sorted(wf_dir.glob('*.yml')) + sorted(wf_dir.glob('*.yaml'))
    if not files:
        return [f'{WORKFLOW_DIR}/ 下没有任何 workflow 文件 —— 结论不可信']

    for path in files:
        rel = f'{WORKFLOW_DIR}/{path.name}'
        text = path.read_text(encoding='utf-8')
        try:
            doc = yaml.safe_load(text)
        except Exception as exc:  # pragma: no cover - YAML 坏了是别的问题
            problems.append(f'{rel} YAML 解析失败：{exc}')
            continue
        if not isinstance(doc, dict):
            continue

        triggers = _triggers(doc)

        # ── 判据 1：不得有 pull_request_target（除显式豁免的） ────────────
        if 'pull_request_target' in triggers:
            reason = _PRT_EXEMPT.get(path.name)
            if reason is None:
                problems.append(
                    f'{rel} 的触发器是 `pull_request_target`：'
                    '它的 workflow 定义**一律取自仓库默认分支**（本仓是 `main`），无视 PR 的 '
                    'base 分支 ⇒ dev 上这份文件里的任何改动（守卫、判据、cron、凭据）'
                    '**全部不会被执行**，跑的还是 main 上那份旧的。'
                    '2025-12-08 生效的平台行为变更（官方 changelog「Actions '
                    'pull_request_target and environment branch protections changes」）。'
                    '应改用 `pull_request`：其定义取自 PR 的 merge commit（dev tip + PR head），'
                    'dev 上的改动立刻生效；且同仓分支的 pull_request 同样有写权限与 secrets。'
                    '若本工作流确由依赖 bot 触发（pull_request 下 token 只读），'
                    '须在守卫的 `_PRT_EXEMPT` 里显式登记理由。'
                )
            else:
                # 豁免项本身也要被核对：它**必须**真的还在用 pull_request_target。
                # 若有人把它迁走了，豁免就该被删掉——否则清单会变成藏污纳垢的地方，
                # 而「豁免项已失效」这件事本身没人会注意到。
                if path.name not in _GUARD_WORKFLOWS:
                    problems.append(
                        f'{rel} 在守卫的 `_PRT_EXEMPT` 里登记了豁免（{reason}），'
                        '但它不在 `_GUARD_WORKFLOWS` 清单里 ⇒ 无法核对它的 checkout 是否显式 ref。'
                        '若它已不再使用 pull_request_target，请把这条豁免删掉。'
                    )

        # ── 判据 2：守卫类工作流的 checkout 必须显式 ref: dev ────────────
        if 'pull_request' not in triggers:
            continue
        if path.name not in _GUARD_WORKFLOWS:
            continue

        for job_name, job in (doc.get('jobs') or {}).items():
            if not isinstance(job, dict):
                continue
            for step_name, ref in _checkout_refs(job):
                if not ref:
                    problems.append(
                        f'{rel} 的 job「{job_name}」用 `pull_request` 触发，'
                        f'但 checkout step（{step_name}）**没写 `with.ref`**。'
                        '`pull_request` 下 checkout 默认检出的是 **merge commit（含 PR 代码）**'
                        '（而 `pull_request_target` 下默认是 base 分支）——'
                        '不显式写 ref 就等于把执行内容交给了 PR 作者：'
                        '他改一下 `scripts/` 就能改掉自己的守卫。'
                        '修法：显式写 `ref: dev`（受信分支）。'
                    )
                    continue
                if ref in _DEFAULT_BRANCH:
                    problems.append(
                        f'{rel} 的 job「{job_name}」用 `pull_request` 触发，'
                        f'但 checkout step（{step_name}）的 `ref: {ref}` 是**默认分支**。'
                        f'默认分支（main）只由发版 PR 推进、落后 dev 上百个提交 ⇒ '
                        '检出的代码与判据都是旧的。'
                        '修法：显式写 `ref: dev`（或 `${{ env.<名字> }}`）。'
                    )
                    continue
                if any(pat in ref for pat in _PR_HEAD_PATTERNS):
                    problems.append(
                        f'{rel} 的 job「{job_name}」用 `pull_request` 触发，'
                        f'但 checkout step（{step_name}）的 `ref: {ref}` **指向 PR 自己的分支**。'
                        '那等于把执行内容完全交给 PR 作者——他改一下 `scripts/` 就能改掉自己的守卫。'
                        '修法：显式写 `ref: dev`（受信分支）。'
                    )

        # ── 判据 4：concurrency.group 必须带过渡期后缀 ──────────────────
        # 过渡期内新旧两版会同时触发；若 group 名相同 ⇒ cancel-in-progress: true 的一方
        # 会取消掉另一方 ⇒ 守卫被静默取消（实测：旧版 success、新版 cancelled）。
        if 'pull_request' not in triggers:
            continue
        if path.name not in _GUARD_WORKFLOWS:
            continue
        if path.name in _SAME_GROUP_EXEMPT:
            continue

        conc = doc.get('concurrency')
        if conc is None:
            # 没有 concurrency 段 ⇒ 不存在互斥风险（也就不需要后缀）。
            # ⚠️ 但**有副作用**的工作流在过渡期会新旧各跑一次（见文件头表格）。
            continue
        if isinstance(conc, str):
            # YAML 允许 `concurrency: my-group` 这种简写形态。
            group = conc
        elif isinstance(conc, dict):
            group = str(conc.get('group') or '')
        else:
            group = ''
        if not group:
            # `concurrency:` 存在但没有 group（如只有 cancel-in-progress）⇒ 判据无从判断。
            problems.append(
                f'{rel} 有 `concurrency` 段但**没有 `group`** ⇒ 无法判断它是否与默认分支'
                '旧版算出了同一个 concurrency group。'
                '若本工作流确实不需要互斥，请把整个 `concurrency` 段删掉；'
                '若需要，请显式写 `group`（并按约定带过渡期后缀）。'
            )
            continue
        if _TRANSITION_SUFFIX in group:
            continue

        problems.append(
            f'{rel} 的 `concurrency.group` 是 `{group}`，**没有过渡期后缀'
            f'（约定含 `{_TRANSITION_SUFFIX}`）**。'
            '迁到 `pull_request` 后，过渡期内 `main` 上的旧版（`pull_request_target`）'
            '与 `dev` 上的新版（`pull_request`）**会同时被触发**；'
            '若两者 group 名相同，`cancel-in-progress: true` 的一方会'
            '**取消掉另一方** ⇒ 守卫被静默取消，'
            '而 GitHub 把 cancelled 记成 check 失败。'
            '实测（PR #2807）：旧版 success、新版 cancelled。'
            '⚠️ 只把新版改成 `cancel-in-progress: false` **不够**——'
            '取消是旧版发起的，新版无论自己是什么设置都会被取消掉。'
            '修法：group 名加过渡期后缀，让新旧两组并存、互不取消；'
            '发版后 `main` 上的旧版被替换 ⇒ 两边 group 名一致 ⇒ 自然恢复。'
        )

    return problems


def main(argv: List[str]) -> int:
    repo = Path(__file__).resolve().parent.parent
    if '--root' in argv:
        idx = argv.index('--root')
        if idx + 1 < len(argv):
            repo = Path(argv[idx + 1]).resolve()

    problems = check(repo)
    if problems:
        print(f'✗ workflow 定义来源守卫：{len(problems)} 处问题')
        for p in problems:
            print(f'  - {p}')
        return 1

    if '--report' in argv:
        print(f'✓ 全仓 `pull_request_target` 仅剩 {len(_PRT_EXEMPT)} 个显式豁免项'
              '（依赖 bot 触发 ⇒ pull_request 下 token 只读）')
        print(f'✓ 守卫类工作流（{len(_GUARD_WORKFLOWS)} 个）checkout 均显式写了非默认分支的 ref')
        print('  （CI 类工作流检出 PR 代码是职责所在，不在本判据范围）')
        print('✓ 无副作用守卫的 concurrency 不会互相取消（过渡期新旧两版并存时不静默取消守卫）')
    else:
        print('OK: workflow 定义来源正确，dev 上的改动对各路径可见。')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

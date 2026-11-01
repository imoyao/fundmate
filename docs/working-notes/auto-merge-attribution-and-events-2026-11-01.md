# auto-merge 归因与合并事件投递 — 2026-11-01

> 类型：实测记录 / 机制说明
> 关联：issue #2799、PR #2800、PR #2797、PR #2802
> 结论：**合并归因 = 启用 auto-merge 的那个凭据；归因决定后续事件是否被投递。**
> 用 GITHUB_TOKEN 启用 ⇒ 合并归因到 `github-actions` ⇒ `pull_request: closed` /
> `push` 事件**全部被抑制** ⇒ 门禁下游的守卫在这条路径上是哑的（假绿）。
> 改用用户 PAT 后事件恢复投递。

## 1. 问题现场

`pr-auto-merge.yml` 用 GitHub 原生 auto-merge（`gh pr merge --auto`）合 PR。
2026-11-01 之前，它用 `secrets.GITHUB_TOKEN` 启用。

PR #2797 是本仓史上第一次真正走 native auto-merge 合并的 PR（此前 189 个 base=dev
合并全是人肉点合）。合并后用户发现：**`Closes #2793` 没生效，#2793 仍是 OPEN**；
同时 `mojibake-dev-guard`（push→dev）与 `dependabot-lockfile-regen`（push→dev）
在该次合并后也都没跑。

而门禁本身是绿的——`质量门禁汇总 = SUCCESS`。这正是「假绿」最典型的形态：
**门禁说通过了，但它下游的守卫一个都没运行。**

## 2. 根因

GitHub 的规则：除 `workflow_dispatch` / `repository_dispatch` 外，
**由 GITHUB_TOKEN 触发的事件不创建 workflow run**。

native auto-merge 是「排队 → 门禁转绿后由 GitHub 执行合并」，
**合并时携带的是最后启用 auto-merge 的那个凭据的归因**。于是用 GITHUB_TOKEN
启用出来的合并，其归因是 `github-actions` ⇒ 合并产生的事件全部落在
「GITHUB_TOKEN 触发」的范围内 ⇒ 被抑制。

实测（`gh api graphql` 查 PR `#2797`）：

```json
{"mergedBy":{"login":"github-actions"},
 "autoMergeRequest":{"enabledBy":{"login":"github-actions"},"mergeMethod":"MERGE"}}
```

### 2.1 交叉对照：四个工作流在两种合并方式下的表现

| 工作流 | 触发类型 | #2796 人肉合并（05:41Z） | #2797 auto-merge（07:10Z） |
|---|---|---|---|
| `close-linked-issues` | `pull_request: closed` | ✅ success | ❌ **无 run** |
| `issue-claim-sync` | `pull_request_target: closed` | ✅ success | ❌ **无 run** |
| `mojibake-dev-guard` | `push` → dev | ✅ success | ❌ **无 run** |
| `dependabot-lockfile-regen` | `push` → dev | ✅ success | ❌ **无 run** |

合并窗口（07:05–07:20Z）内全仓 workflow run 总数 = **1**，唯一那条是
`dynamic/github-code-scanning/codeql`（GitHub **内建**分析，非仓库工作流）
⇒ 排除「卡在待批准队列」这类替代解释。

### 2.2 反直觉的排除项

GitHub Support 的常见建议是「closed 事件改用 `pull_request_target`」。
但本仓 `issue-claim-sync.yml` 用的**正是** `pull_request_target: closed`，
对 #2797 同样无 run ⇒ 问题不是「merge-commit job 没排」，而是**整个事件被归因抑制**。
照官方建议改是白改。

### 2.3 外部独立实证

ebi-agent-chat-relay 仓库（2026-09-22，16 次合并对照，1:1 相关无例外）：

> A merge attributed to GITHUB_TOKEN fires no push or pull_request event.
> A merge attributed to a real user does. … The token that last enables
> auto-merge determines the eventual actor.

该仓库还给出两条易错的推论，本仓同样适用：

- `issues: write` 权限**不能**救 bot 归因的合并——auto-merge 是事后由 GitHub 执行的，
  不携带启用作业的权限；
- 想让**自己的** PR 走通 auto-merge 路径，启用方必须是用户凭据。

## 3. 修复

`.github/workflows/pr-auto-merge.yml` 改用 secret `AUTO_MERGE_PAT`（用户 PAT）：

```yaml
env:
  GH_TOKEN: ${{ secrets.AUTO_MERGE_PAT }}
```

**刻意不写 `|| secrets.GITHUB_TOKEN`**：PAT 缺失时静默回落 = 假绿原样装回来，
而且没有任何人看得见。改为 PAT 为空时 `exit 1` 显式失败，把「没配 PAT」与
「PR 有冲突」分开（后者本就该重试）。

顺带用 `gh api user` 确认凭据真是用户身份（GITHUB_TOKEN 的 API 身份是
`github-actions`，PAT 的是它的主人）——归因看的就是这个身份。

守卫 `scripts/guard_auto_merge_user_attribution.py`（并入 `ci.yml` 的 `scripts_test`，
阻断）把六条钉死：必须用用户 PAT / 不许 `||` 回落 / PAT 缺失必须显式失败 /
必须留归因说明（防「顺手改回 GITHUB_TOKEN」时的无声退化）/
**触发器不得是 `pull_request_target`**（否则本节所有修复都不会被执行，见 §4.2）/
**fork PR 必须被显式跳过**（fork 拿不到 secrets，不跳过会误报成「没配 PAT」）。
回归网 `scripts/tests/test_auto_merge_user_attribution.py`（**13 个变异探针**）。

## 4. 端到端复验（同仓 A/B 对照）

> ⚠️ **本节初版（2026-11-01 上午）的判断已被当晚的实测推翻并更正**：
> 初版写「`pull_request_target` 跑的是 **base 分支**的 workflow 文件」——**错的**。
> 真相见 §4.2：它跑的是**默认分支**（`main`）。初版那句注解是本仓踩过的坑，留着做警示。

### 4.1 修复前后的对照（更正后）

| PR | 贴标签时刻 dev 的 tip | 实际执行的是哪份定义 | `mergedBy` | 关联 issue |
|---|---|---|---|---|
| `#2800` | 旧版（改动尚未合入） | `main` 上的旧版 | `github-actions` | `#2799` 仍 OPEN ❌ |
| `#2801`（探针） | **已含新版的 `57f35e9a6`** | **仍是 `main` 上的旧版** | `github-actions` | `#2799` 仍 OPEN ❌ |

两次都是 bot 归因。**`#2801` 是关键的反证**：它的 base=dev，且 dev 的 tip 早在
**08:58:27** 就已包含带 PAT 的新版定义，而探针 run（`41291802250`）在 **09:08:35**
才触发——晚了整整 10 分钟，dev 上新版早已就位，跑的却仍是旧版。

判据：新版 workflow 里那行 `启用 auto-merge 的凭据身份：$actor` 的 echo
**没有出现在日志里**；日志里的 `echo "已为 $PR_URL 启用 auto-merge（质量门禁汇总转绿后
自动合入 dev）"` 与 `main` 上的旧版**逐字一致**。

### 4.2 第二层根因：`pull_request_target` 的定义只取自默认分支

2025-12-08 生效的平台行为变更（官方 changelog「Actions pull_request_target and
environment branch protections changes」）原文：

> The `pull_request_target` event now always uses the default branch for workflow source
> and reference: The workflow file and checkout commit will always be taken from the
> repository's **default branch, regardless of the pull request's base branch**.

本仓默认分支 = `main`（`gh api repos/imoyao/fundmate --jq .default_branch`），
功能 PR 一律 base=`dev` ⇒ **dev 上这份 workflow 的任何改动对这条路径都不可见**。

同仓 A/B 对照（用 `ci.yml` 当天然探针——它在 main 与 dev 上不同）：

| 事件 | 定义的来源 | 证据 |
|---|---|---|
| `pull_request` | **merge commit**（dev tip + PR head） | PR `#2800` 的 `pull_request` run 步骤里**有**「自动合并的归因（阻断）」这一步，而 `main` 版 `ci.yml` 里没有这一步 |
| `pull_request_target` | **默认分支 `main`** | PR `#2801` 的 run 执行的是 `main` 版 `pr-auto-merge.yml`（旧文案），尽管 dev tip 已是新版 |

⇒ **PAT 修复躺在 `dev` 上，从一开始就不会被执行。**

### 4.3 修复方向

改触发器为 `pull_request`（其定义取自 merge commit ⇒ dev 上的改动立刻生效），
且同仓分支的 `pull_request` 同样有写权限与 secrets（官方文档：fork 才受限），
本仓所有功能分支都在本仓内 ⇒ **不损失任何能力**。

换触发器后守住三条边界：

1. **不 checkout PR 代码**——本工作流只用 `gh` 调 API，无 pwn request 面；
2. **显式跳过 fork PR**——fork 拿不到 secrets，不跳过会误报成「没配 PAT」而误红；
3. 守卫新增两条判据：触发器不得是 `pull_request_target`、fork 必须被显式跳过。

### 4.4 修复后的复验：四项证据全部到手

修复 PR `#2802` 合入 dev（`354c192fc`）后，两个探针 PR 取证：

**探针 `#2804`**（正文未写 closing keyword）：验证归因与 `push` 事件投递。

| 证据 | 结果 |
|---|---|
| 合并归因 | `merged_by = imoyao` ✅（此前是 `github-actions[bot]`） |
| `push` 到 dev 的事件投递 | `乱码守卫（dev push）` + `Dependabot 锁重生成` 均产生 run ✅ |
| `pull_request: closed` 投递 | `自动关闭关联 issue（dev 合入）` 产生 run ✅ |
| issue 自动关闭 | ❌ 未关 —— 日志原文「`#2804` 正文里没有可关闭的 closing keyword，无需操作」⇒ **是探针正文的问题，不是链路的问题**（AGENTS.md 早有此告警） |

**探针 `#2805`**（正文带真正的 `Closes #2799`）：补上第四项。

| 证据 | 结果 |
|---|---|
| 合并归因 | `mergedBy = imoyao`（`mergedAt = 2026-11-01T10:27:12Z`）✅ |
| 合并窗口内的事件投递 | `乱码守卫（dev push）`、`Dependabot 锁重生成`、`自动关闭关联 issue（dev 合入）` 三条 run 均产生 ✅ |
| issue 自动关闭 | `#2799` → `CLOSED`（`closedAt = 2026-11-01T10:27:22Z`），时间线里 `closed` 的 actor = `github-actions[bot]` ✅ |
| 关闭动作日志 | `已关闭 #2799「[bug] native auto-merge 合并抑制全部仓库工作流事件：…」—— 由 #2805 合入 dev 触发。` ✅ |

⇒ **两层根因的修复全部验证通过**：PAT 归因恢复了合并事件的投递，
门禁下游的守卫（issue 自动关闭 / 乱码扫描 / lockfile 重建）在这条路径上重新工作。

### 4.5 残留：过渡期内 `main` 旧版与 `dev` 新版竞跑

修复合入 dev 后，**`main` 上那份旧版 `pr-auto-merge.yml` 仍然带 `pull_request_target`**
⇒ 贴 `automerge` 标签时两条路都会触发：

| 路径 | 定义来源 | 凭据 | 谁跑得快 |
|---|---|---|---|
| 旧版 | `main`（`pull_request_target`） | `GITHUB_TOKEN` | **快**（无需算 merge commit，脚本也更短） |
| 新版 | `dev`（`pull_request`） | 用户 PAT | 慢 |

实测 `#2802` 贴标签时**旧版抢先**：新版 run 的日志是
`auto-merge 暂未启用… GraphQL: Merge already in progress (mergePullRequest)`，
该 PR 最终 `merged_by = github-actions[bot]` ⇒ 归因仍是 bot。

**这不影响上面的四项证据**（那两轮是用 PAT 直接启用 auto-merge 取证的，
等价于新版 workflow 内部执行的那一步），但**说明在 `main` 同步新版定义之前，
自动合并这条路径仍会被旧版抢走**。

处置：随下次 `dev → main` 发版自然解决（发版会把 `dev` 上这份文件带过去），
或按 `#2803` 的选项单独处理。**在此之前，不要指望「贴标签 → 自动合并」这条
自动化路径已完全正常** —— 它只在旧版抢不到时生效。

### 4.6 处置 `#2803` 时挖出的第三条机制：依赖 bot 的 PR **不能**迁 `pull_request`

上一节 4.2 的结论是「`pull_request_target` 的定义只取自默认分支 ⇒ 应迁到
`pull_request`」。迁 `#2803` 时发现这句话**只对一半场景成立**。

GitHub 官方文档（events-that-trigger-workflows，`pull_request` → "Workflows in forked
repositories"）原文：

> Workflows triggered by Dependabot pull requests are treated as though they are from a
> forked repository, and are also subject to these restrictions.
> The `GITHUB_TOKEN` has read-only permissions in pull requests from forked repositories.

⇒ **Dependabot 的 PR 即使 head 仓库就是本仓**（实测 `#2645`–`#2649` 的 head_repo 都是
`imoyao/fundmate`），在 `pull_request` 事件下 token 仍是**只读**、secrets 也不注入。

**「head 仓库相同」≠「权限相同」** —— Dependabot 被平台特殊对待。

这条如果漏掉，后果是：`dependabot-auto-merge.yml` 的 `gh pr merge --auto` 与
`dependabot-lockfile-regen.yml` 的 `git push` **必然失败**（`#578` 同族事故）。
而且它**不会在 CI 里暴露** —— CI 全绿、PR 合得进去，只有真正跑起来才炸。

发现路径也值得记：仓库里**已有一条守卫**
（`scripts/guard_dependabot_lockfile_regen.py`）明确要求「触发方式必须是
`pull_request_target`」，理由写的就是这句。本仓自己的判据比通用文档更早知道这件事。
⇒ **改仓库里的 CI 之前，先读仓库里已有的守卫**——它们记录的是事故，不是文档摘要。

### 4.7 迁移到 `pull_request` 的第二处易漏点：checkout 必须显式 `ref`

| 事件 | `actions/checkout` 默认检出 |
|---|---|
| `pull_request_target` | **base 分支**（受信） |
| `pull_request` | **merge commit（含 PR 代码）** |

⇒ 迁移时若没补 `ref`，等于把「执行内容」交给 PR 作者：
把 `guard_pr_four_questions.mjs` 的判据改成恒真、把 `pr-overlap-guard.yml` 的
`GOV_GLOB` 改空——**改的是守卫自己**。

本仓有 3 个工作流的 checkout 原本没写 ref（`issue-claim-sync` /
`pr-four-questions-guard` / `pr-overlap-guard`），迁移时都补上了 `ref: dev`。

**例外**：`ci.yml` / `docker-build.yml` / `ai-review.yml` 检出 PR 代码是**职责所在**
（CI 就是用来测 PR 的代码的），要求它们写 `ref: dev` 反而让 CI 测错东西。
⇒ 守卫用**显式清单**区分「守卫类」与「CI 类」，不靠猜。

### 4.8 迁移的第三处易漏点：`concurrency` 的互斥会让守卫被**静默取消**

这是迁移 `#2803` 时**实测撞到**的（PR #2807 首次 CI），同一时刻两个 run：

| run | event | 结论 |
|---|---|---|
| 41305286670 | `pull_request`（`dev` 上的新版） | **cancelled** |
| 41305286732 | `pull_request_target`（`main` 上的旧版） | success |

⇒ 过渡期内 `main` 旧版与 `dev` 新版**同时被触发**，而两者算出的
**concurrency group 名字相同**（group 名只含 PR 号，不含事件名）
⇒ `cancel-in-progress: true` 让两者**互相取消** ⇒ **守卫被静默取消**，
而 GitHub 把 `cancelled` 记成 check 失败（PR 上显示 fail）。

**这个缺陷是迁移引入的**：迁移前只有一个版本生效（都读 `main`），不存在并发。

修法分两类：

| 工作流 | 有无副作用 | 修法 |
|---|---|---|
| `pr-four-questions-guard` | 无（只读正文、只返回退出码，不评论不写标签） | 改 `cancel-in-progress: false` ⇒ 两份串行跑完，结论一致、无害 |
| `pr-overlap-guard` | 有（会评论 PR） | 过渡期跑两次可能发两条相同评论（可接受）；**有副作用**的不能靠 `false` 解决，得用不同 group 名避开互斥 |
| `pr-auto-rebase` | 有（会推分支） | 但幂等（第二次因「分支已是最新」跳过）⇒ 无害 |

守卫 `scripts/guard_workflow_definition_source.py` 的判据 4 盯住这条：
无副作用守卫的 `cancel-in-progress` 不得为 `true`。

## 5. 边界

- **dependabot 那条路径刻意不动**（`dependabot-auto-merge.yml`）：它的合并归因留在
  bot 侧是产品决策（依赖更新不该触发版本自增、不该重启 bot 链），属另一条议题。
- **另外 4 处 `secrets.GH_PAT || secrets.GITHUB_TOKEN`**（`claim-sync.yml` /
  `cnb-github-backfill.yml` / `bridge-*.yml`）与本条无关：那是 CNB 侧凭据的既有惯例，
  仓库 Actions secrets 里**并没有** `GH_PAT`，那几处一直在走 GITHUB_TOKEN 回落。
  刻意不共用 secret 名，避免连带改变它们的推送归因而引入递归防护问题。
- **PAT 有效期**：过期后 ② 自动合并这一步会红（`gh api user` 失败 → `exit 1`），
  而非静默退化——这是有意设计，但需人工续期。
- **本仓另有 6 个工作流也用 `pull_request_target`**（`dependabot-auto-merge` /
  `dependabot-lockfile-regen` / `issue-claim-sync` / `pr-auto-rebase` /
  `pr-four-questions-guard` / `pr-overlap-guard`）⇒ **它们同样只跑 `main` 上的定义**。
  平台级行为带来的系统性问题，已另开 issue 统一处理，不在本次修复范围内。

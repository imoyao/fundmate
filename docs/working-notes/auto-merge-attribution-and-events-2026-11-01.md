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

实测（`gh api graphql` 查 PR #2797）：

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
阻断）把四条钉死：必须用用户 PAT / 不许 `||` 回落 / PAT 缺失必须显式失败 /
必须留归因说明（防「顺手改回 GITHUB_TOKEN」时的无声退化）。
回归网 `scripts/tests/test_auto_merge_user_attribution.py`（7 个变异探针）。

## 4. 端到端复验（同仓 A/B 对照）

同一个 PR（#2800）先后经历了两种归因，构成天然对照：

| 合并 | 启用方 workflow 版本 | `mergedBy` | 合并窗口内的仓库工作流 run | 关联 issue |
|---|---|---|---|---|
| #2800（第一次） | **dev 上的旧版**（GITHUB_TOKEN） | `github-actions` | **0 个** | #2799 仍是 OPEN ❌ |
| #2802（探针） | **dev 上的新版**（`AUTO_MERGE_PAT`） | 用户 | 见下 | 自动关闭 ✅ |

> 注：`pull_request_target` 跑的是 **base 分支**的 workflow 文件，所以 #2800 自己
> 贴标签时用的是 dev 上的旧版——它的合并因此仍是 bot 归因、事件仍被抑制。
> 这恰好成了「修复前」那一侧的现成样本；改动合入 dev 后的下一个 PR 才是「修复后」。

## 5. 边界

- **dependabot 那条路径刻意不动**（`dependabot-auto-merge.yml`）：它的合并归因留在
  bot 侧是产品决策（依赖更新不该触发版本自增、不该重启 bot 链），属另一条议题。
- **另外 4 处 `secrets.GH_PAT || secrets.GITHUB_TOKEN`**（`claim-sync.yml` /
  `cnb-github-backfill.yml` / `bridge-*.yml`）与本条无关：那是 CNB 侧凭据的既有惯例，
  仓库 Actions secrets 里**并没有** `GH_PAT`，那几处一直在走 GITHUB_TOKEN 回落。
  刻意不共用 secret 名，避免连带改变它们的推送归因而引入递归防护问题。
- **PAT 有效期**：过期后 ② 自动合并这一步会红（`gh api user` 失败 → `exit 1`），
  而非静默退化——这是有意设计，但需人工续期。

# 分支收敛评估（2026-08-19，对照 main-v2）

## 一、探市页用户添加的数据类型（影响 #821 迁移落点）

现状（frontend/src/views/explore/index.vue 的 handleAdd / addHotAsset）：
- 用户输入字段仅 `symbol / name / type / costPrice / quantity` —— 即**持仓快照**（含份额+成本价）。
- 经 `addHolding()` 写入 `useLocalHoldings`（localStorage）。
- **无任何交易记录字段**（无交易日期、买卖方向、账户、手续费），即不支持交易流水。

结论：
- 探市页**只支持添加当前持仓快照，不支持交易记录**。添加交易记录是重操作（涉及日期/方向/账户/手续费/对账/流水表 schema），当前无此能力。
- 因此对 #821「登录后迁移」而言：既然只有持仓快照，**迁移直接写 positions 表（持仓域）最简单正确**，不需要写 transactions 流水表。
- 待定：探市页填了成本+份额的持仓，登录后迁移成「真实持仓 positions」还是「自选观察项 watchlist」？倾向 positions（用户意图是记账）。

## 二、各分支 vs main-v2 评估

| 分支 | 领先提交 | 改动量 | 状态 | 建议 |
|---|---|---|---|---|
| refactor/god-pages-split | 7 个（#980/#995 前端 Overview/watchlist/login 重构） | +1774/-959 | 半成品，有价值 | **保留**，待 Overview 完工后单独提 PR 合入 |
| wip/holding-import-frontend-draft | 1 个（24413ab 导入向导草案） | 删 1042 行 orchestrator、删测试 | **已过时** | **保留但标记废弃**，与已合入的 split-import-wizard 方向相反，不合入，待按新方案重做 |
| feature/jigu-migration | 1 个（c421f42 跨 Supabase 迁移脚本） | 运维脚本 | 独立、无害 | **可合并**（纯 scripts，不碰主代码） |
| feature/ai-recognizer-agent | 1 个（83c7693 账本精灵 Agent 骨架） | 新功能骨架 | 半成品 | **保留**，独立功能线 |
| feature/sso-cross-subdomain | 1 个（649b41a OAuth 修复，但误删 1630 行核心文件） | +173/-1630 | ⚠️ 危险 | **整体禁止合入**；仅可 cherry-pick 11 行 login 修复，误删的 11 个核心文件（双库测试/文档）必须先在目标分支恢复 |

### 关于 feature/sso-cross-subdomain（初判为"事故"，经核实为误判，已更正）
- 实际修复（649b41a）：login/index.vue 11 行，`onGithubLogin` 的 redirectTo 由 `/welcome` 改根路径（hash 模式编码异常）。修复本身有价值，**main-v2 当前 login 仍存在该 bug（第327/357行）**，故修复仍需合入。
- 初判"误删 1630 行核心文件"是**误判**：`git diff main-v2..sso` 显示的大量"删除"是因为 **sso 分支基点很旧**（早于 main-v2 上那些文件的新增），并非 sso 主动删文件。sso 分支本身没有破坏代码。
- 正确处置（2026-08-19 已执行）：**不 merge 整个 sso 分支**（会带入大量旧基点差异造成倒退）；改为 `git cherry-pick 649b41a` 单独把 OAuth 修复取到 main-v2（提交 `972b6d7`，干净无冲突）。sso 分支保持原状、不做任何"恢复"操作（恢复反而会把 main-v2 新代码灌入，才是真破坏）。

## 三、收敛行动计划（执行记录 2026-08-19）
1. **main-v2 锚点提交**：`3d95317` 先提交本评估文档，确保后续操作可找回。
2. **已合并 feature/jigu-migration**：`git merge --no-ff`（纯运维脚本，零冲突，+176 行）。
3. **已 cherry-pick sso 的 OAuth 修复**：`972b6d7`（仅 login 11 行），未合整个 sso 分支（避免旧基点倒退）。
4. **保留待完工**：refactor/god-pages-split（Overview 完工后提 PR）、feature/ai-recognizer-agent（骨架，独立线）。
5. **标记废弃**：wip/holding-import-frontend-draft（已被 split-import-wizard 取代，待按新方案重做，不合入）。
6. **#821 后续**：确定迁移落点（positions 还是 watchlist）后，从 main-v2 切 fix 分支实现，不碰 god-pages-split 碰过的文件，零冲突。

## 四、待用户决策（仍未决）
- 探市页迁移落点：positions（持仓）还是 watchlist（观察项）？倾向 positions。
- 是否允许探市页未来支持交易记录（重操作）？当前不支持，建议暂不做。
- 注意：god-pages-split 的 login 重构（含旧 /welcome bug）合入 main-v2 时需带上 972b6d7 的 OAuth 修复，可能需解决冲突。

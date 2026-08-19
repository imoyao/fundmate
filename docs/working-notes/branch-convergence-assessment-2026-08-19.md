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

### ⚠️ feature/sso-cross-subdomain 事故详情
- 实际修复（649b41a）：login/index.vue 11 行，`onGithubLogin` 的 redirectTo 由 `/welcome` 改根路径（hash 模式编码异常）。修复本身有价值。
- 但分支 diff 显示误删了以下核心文件（这些在 main-v2 上均存在且为权威）：
  - backend/tests/core/test_db_data_domain.py（双库架构核心回归测试）
  - backend/tests/core/test_cross_domain.py
  - backend/tests/domains/test_watchlist.py
  - docs/dev/db-data-domain.md（双库权威文档）
  - docs/spec/architecture.md / changelog.md / index.md
  - docs/backend-restructure-edgeone-dualengine.md
  - docs/privacy.md
  - docs/working-notes/code-audit-and-remediation-2026-08-01.md
- 原因判断：agent 把未跟踪/被忽略文件当成脏改动一并 `git clean` 或误删。若整体合入会摧毁双库架构测试与文档。
- 处置：不合入该分支；如需那个 OAuth 修复，单独 `git checkout main-v2 -- <被删文件>` 恢复，再 cherry-pick 649b41a 的 login 改动。

## 三、收敛行动计划（建议）
1. **main-v2 保持干净**：不接收 sso 分支、不接收 wip 草案。
2. **可立即合入**：feature/jigu-migration（纯脚本，零冲突风险，可提 PR 合入 main-v2）。
3. **保留待完工**：refactor/god-pages-split（Overview 完工后提 PR）、feature/ai-recognizer-agent（骨架，独立线）。
4. **标记废弃**：wip/holding-import-frontend-draft（注明"已被 split-import-wizard 取代，待按新方案重做"）。
5. **修复 sso 事故**：在 feature/sso-cross-subdomain 上先 `git checkout main-v2 -- <11 个被删文件>` 恢复，再评估 OAuth 修复是否还需（可能已在新 login 重构中覆盖）；清理后该分支才可提 PR。
6. **#821 后续**：确定迁移落点（positions 还是 watchlist）后，从 main-v2 切 fix 分支实现，不碰 god-pages-split 碰过的文件，零冲突。

## 四、待用户决策
- 探市页迁移落点：positions（持仓）还是 watchlist（观察项）？倾向 positions。
- 是否允许探市页未来支持交易记录（重操作）？当前不支持，建议暂不做。
- 是否现在合并 feature/jigu-migration？

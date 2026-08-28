# 基金E账户与聚合前端数据模型设计（#1101，证据版 v2）

> 关联 issue：#1101（作者 imoyao）。本文基于**实际代码核查**（非假设）收敛设计，供决策后落地。
> 状态：**v2 证据版**，待用户确认最后 2~3 个微决策。未实施任何代码改动。
> Worktree：`D:/codes/fundmate-wt/1101-design`，分支 `docs/1101-e-account-aggregation`，基于 `origin/dev` `692d8ac`。

## 0. 结论先行（精炼）

1. **E账户不当普通账户显示** → 账户列表过滤掉它（保留 `ledger_type='e_account'` 作为内部实现，但隐藏出用户账户列表），并新增"跨账本基金聚合视图"。
2. **聚合前端（同花顺/东方财富）不当实体建模** → 仅在 `ledgers` 加一个**展示用可选字段 `frontend_app`**，无业务逻辑、无新表。
3. **银行卡绑定 / 数据来源 / 导入溯源** → 现有模型已覆盖，**不新增任何表或冗余字段**。
4. **实际最小 schema 变更只有两列**：`ledgers.frontend_app`（新增）+ `ledgers.is_aggregation`（新增，用于列表过滤，避免硬编码 `'e_account'`）。

## 1. 实证核查（当前代码事实，带 file:line）

| 用户提案 | 代码现状 | 结论 |
|---|---|---|
| 新增 `data_source` 枚举字段 | `Position.source` 已是来源枚举（`PositionSource`：`manual`/`e_account_holding`/`ai_holding`/`file_import` 等，`app/core/constants.py:164`） | **冗余，复用 `source`** |
| 新增 `position_import_meta` 式溯源 | 表已存在（`positions/models.py:86`），含 `source_broker`/`fund_manager`/`fund_account`/`trade_account`/`raw_extra`(JSON) + E账户对账字段 `is_attributed`/`is_ignored` 等 | **已具备，勿重建** |
| E账户"不作为 ledger_type" | 导入流程 `get_or_create_e_account_ledger()`（`importer/orchestrator.py:868`）创建 `ledger_type='e_account'`；`ledger_service.py:135`、`ledgers/views.py:207,938,945` 均耦合此类型；测试 `test_orchestrator_holdings.py:36,64`、`test_upsert_from_holding.py:25` 断言此类型 | **去掉是高成本迁移，本次不删** |
| 新增 `frontend_app` / `access_channel` | `ledgers` 模型（`ledgers/models.py`）无此字段 | **唯一干净的新增字段** |
| 银行卡绑定新表 | `ledgers.linked_cash_ledger_id` 已把现金账本绑到账户所属机构；`positions.source_broker` 记录来源平台 | **现有模型足够** |
| 证券账号持货基需新类别 | `positions.asset_type` 独立于 `ledgers.ledger_type`，broker 账本下可挂 fund 类持仓 | **无需新类别，仅展示分组** |

**关键事实**：E账户导入已落地为"一个 `e_account` 账本 + 若干 `positions`（`source='e_account_holding'`，部分 `ownership_status='shadow'` 用于对账）"。它**已经是**一种聚合数据源，只是被错误地展示在账户列表里。

## 2. 概念模型（采纳用户修正）

- **基金E账户** = 中登官方 App 提供的**一站式公募基金查询服务**（数据源，非只读视图比喻）。限定：仅场外份额、仅公募、T-3 延迟。用户可把查询结果录入为持仓补充来源。
- **同花顺集团**含两个法人：同花顺网络（交易前端软件，无牌照）+ 同花顺基金销售（持牌，运营"爱基金"）。用户在同花顺 App 买基金，底层交易对手是**爱基金**（销售机构），账户开在爱基金，银行卡绑爱基金。前端与销售机构是同一集团下不同法人。
- **聚合前端**（同花顺/东方财富）= 第三方行情软件，绑定多家券商账户做统一查看，**不持有任何资产**，仅是展示/聚合层。
- **银行卡** = 资产账户（记录余额），绑定到"实际持有该账户的机构的账本"（证券公司或基金销售机构），不绑纯前端。

## 3. 数据模型变更（最小集）

### 3.1 `ledgers` 新增两列（均 additive，低风险）
- `frontend_app`：`VARCHAR(20)`，可空。枚举 `tonghuashun`/`eastmoney`/`self`/`other`。**仅展示**——"我通过哪个前端查看这个账户"，不参与任何计算。
- `is_aggregation`：`Boolean`，默认 `False`。标记"聚合/系统账本"，账户列表过滤 `is_aggregation != True`。E账户导入创建时置 `True`（替代在列表查询里硬编码 `'e_account'`）。

### 3.2 明确"不做什么"（避免过度设计）
- **不**新建 `broker_aggregator_links` 表 / `is_aggregator` 标记 / `trading_frontend` 复杂字段——聚合前端只是 `frontend_app` 标签。
- **不**新建银行卡绑定关系表——`linked_cash_ledger_id` 已够。
- **不**新增 `data_source` 字段——复用 `Position.source`。
- **不**去掉 `ledger_type='e_account'`——迁移成本高于收益；以"隐藏+聚合视图"达成概念等价（见 §4）。后续若确有必要再单独评估清理。
- **不**为证券账号货基新建 Ledger 类别——broker 账本下 `positions.asset_type='fund'` 即可，前端详情内分组展示。

### 3.3 本期不新增可选字段
- 经复核，`funding_account`（资金来源银行卡）无具体功能驱动，且产品不做交易流水，本期不新增；如需低频扩展可用既有 `position_import_meta.raw_extra`(JSON) 兜底。

## 4. 前端方案（采纳"概览卡片 + 下钻"）

**E账户 = 资产概览里的聚合卡片，点击下钻到基金明细页**，不当独立顶层页面。

- **资产概览**：基金资产卡片显示"场外基金（含E账户）: XX元"，E账户汇总数直接并入总资产，不割裂全局感。
- **下钻页（基金明细）**：
  - **主视图：按基金产品聚合**——每只基金总份额/总市值 + 持有机构列表（"在支付宝 X 份、在爱基金 Y 份"）。最贴合用户心智。
  - **筛选/切换**：按销售机构（支付宝/爱基金/银行/同花顺…）；按购买应用（`source_broker` / `frontend_app`）。
  - **下钻**：点基金 → 各销售机构持仓明细。
  - **对账条**：E账户导入数据（`source='e_account_holding'`）vs 用户手动基金持仓合计，差异高亮（复用 `ownership_status` + `position_import_meta`）。
- **账户列表**：过滤 `is_aggregation=True`（即隐藏 E账户）；其余分组/排序不变。
- **账户详情（broker）**：持仓按资产类别分组（股票 / 场内货基 / …），Ledger 类别仍为券商。

## 5. 与用户提案的对照

| 用户提案 | 采纳情况 |
|---|---|
| §二 聚合前端仅作 ledger 可选标签 | ✅ 采纳 → `ledgers.frontend_app` |
| §三 默认按基金产品聚合 + 机构筛选 + 下钻 | ✅ 采纳 → 前端方案 |
| §四 银行卡现有模型足够 | ✅ 采纳 → 不新增 |
| §五 E账户作概览卡片+下钻，不当独立页 | ✅ 采纳 → §4 |
| §六.1 `ledgers.frontend_app` | ✅ 采纳 |
| §六.2 `data_source` | ⚠️ 冗余，复用既有 `Position.source`（`PositionSource` 枚举） |
| §六.4 E账户不作为 `ledger_type` | ⚠️ 概念认同，但**本次保留 ledger_type**（迁移成本过高），以"隐藏+聚合视图"达成等价；清理留待后续 |

## 6. 待决微决策（请拍板）

- **M1.** `is_aggregation` 标记 vs 列表查询直接 `ledger_type != 'e_account'`？→ 建议加标记（前向兼容未来聚合账本，且避免散落硬编码）。
- **M2.** E账户展示入口：资产概览卡片下钻（推荐）vs 独立页面？→ 按 §4 推荐卡片+下钻。
- **M3（已移除）**：`funding_account` 无功能驱动，已从设计删除，不落地。

## 7. 分期落地

- **P0（回应 issue 主诉求，零风险）**：① `ledgers` 加 `is_aggregation` + `frontend_app` 两列；② 账户列表过滤 `is_aggregation`；③ 资产概览基金卡片 + 下钻聚合页（按基金产品默认、机构/应用可筛）；④ E账户导入创建时置 `is_aggregation=True`。
- **P1（可选增强）**：`frontend_app` 在前端账户编辑/展示落地。
- **P2（后续清理，独立评估）**：是否彻底去除 `ledger_type='e_account'`，纯由 `Position.source` 聚合——需单独迁移方案与测试改造，不在本期。

---

*本草案 v2 已用实际代码核查修正 v1 的过度设计（删去 broker_aggregator_links / 银行卡绑定表 / data_source 冗余字段 / 独立货基视图）。所有结论均有 file:line 证据。*

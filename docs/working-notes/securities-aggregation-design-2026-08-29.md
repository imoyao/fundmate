# 场内证券（股票/ETF/可转债）聚合卡片设计（#1132，证据版）

> 关联：#1101（基金E账户聚合，已落地）、#1136（channel_category 重设计，已合 dev）。
> 本文件是 #1132 的实现前设计，供决策后落地。状态：待用户确认 D1~D4。
> 工作树：`D:/codes/fundmate-wt/securities-aggregation`，分支 `feat/securities-aggregation-1132`，基于 `dev`（`75ad61d7` 已含 #1136）。

## 0. 结论先行

本功能（#1132）是 #1101 场外基金聚合的**互补集**：把跨多个券商/股票账本持有的 **股票 + ETF + 可转债（即全部场内证券）** 持仓，聚合成一张"场内证券（股票/ETF/可转债）"概览卡片，点击下钻到明细页（按产品/按券商/按App 三维度），与现有"场外基金（含E账户）"卡片并列。

**最小改动、零 schema 迁移**：完全复用 #1101 已落地的 position 级聚合范式，不新建虚拟账本、不加列。

## 1. 实证核查（现有场外基金聚合，带 file:line）

| 层 | 落点 | 说明 |
|---|---|---|
| 后端服务 | `backend/app/services/fund_aggregation.py:31` `get_fund_aggregation(session, family_id, dimension)` | **position 级**聚合：`Position.query.filter(asset_type.in(('fund','money_fund')), ownership_status=='active')`（`:21,39-47`） |
| 金额口径 | `fund_aggregation.py:24` `_position_market_value_cents` | 复用全局口径 `shares×price×rate → 整数分`，避免浮点累积 |
| 端点 | `backend/app/domains/ledgers/views.py:81-89` `GET /api/ledgers/fund-aggregation/` | `dimension` 校验 `product\|institution\|app`，调 `svc_get_fund_aggregation` |
| 前端卡片 | `frontend/src/views/asset/ledgers/index.vue:135-161` | "场外基金（含E账户）"汇总卡，整卡可点 → `goToFundAggregation()`（`:558-560` → `router.push({name:"fund-aggregation"})`） |
| 前端取数 | `ledgers/index.vue:628-635` `fetchFundTotal()` → `getFundAggregation("product")` | 与账户列表解耦、失败静默兜底 |
| 类型/API | `frontend/src/api/ledger.ts:444-509` | `FundAggregationResult = {total_market_value_cents, dimension, groups[]}`，维度 `product\|institution\|app` |
| 下钻页 | `frontend/src/views/asset/fund-aggregation/index.vue` + 路由 `router/modules/asset.ts:179-186`（`name:"fund-aggregation"`） | 总市值卡 + `el-radio-group` 切维度 + 分组表（product 维度含 `sources` 来源账本列表） |

**关键事实**：聚合计算本身是 position 级（按 `asset_type` 过滤），与"E账户虚拟账本 + `is_aggregation` 隐藏"是正交的两件事。E账户虚拟账本只是"隐藏该账本出用户列表"的手段，聚合并不依赖它（`fund_aggregation.py:20` 注释明确"E账户仅覆盖场外份额，故聚合不含 ETF/LOF 等场内品种"——#1132 正是此互补集）。

## 2. 场内证券数据模型（实证）

- `Position.asset_type`（列名 `type`，`positions/models.py:26`）取值 `stock`/`fund`/`etf`/`bond`/`money_fund`。**ETF = `asset_type='etf'`，可转债 = `asset_type='bond'`，股票 = `asset_type='stock'`**（可转债由 `symbol_utils.py:41-120` 按代码段判定为 `bond`；股票为 A股场内品种）。
- 场内证券持仓挂在 `ledger_type='stock'`（证券账户）账本下（`ledgers/models.py:50-57`），**不存在**场内证券专用虚拟/聚合账本。
- positions 表**无** `venue`/`exchange` 字段（`market` 是 CN_A/CN_HK/US，非场所）；`venue`(EXCHANGE/OTC) 概念仅存在于 watchlist 域，且推断规则为"`asset_type=='fund'`→OTC，否则→EXCHANGE"。即**场内证券 = `asset_type ∈ {etf, bond}`**（按用户收窄口径 ETF/可转债）。

## 3. #1132 设计方案（镜像 fund_aggregation）

### 3.1 后端（新增，不改动现有表）
- 新增 `backend/app/services/securities_aggregation.py`：`get_securities_aggregation(session, family_id, dimension)`，过滤 `asset_type.in(('etf','bond','stock'))` + `ownership_status=='active'`，分组逻辑与 `fund_aggregation` 完全一致（product 按 `symbol` 含 `sources`；institution 按 `ledger.sales_institution_id` 缺省 `"unknown"`；app 按 `ledger.frontend_app` 缺省 `"self"`）。
- 金额口径**复用** `_position_market_value_cents`（建议抽为 `services/_aggregation_common.py` 共享，或本服务内联同逻辑，避免跨文件耦合；以最小改动为准，先内联复用逻辑）。
- 新增端点 `GET /api/ledgers/securities-aggregation/`（见 D4 命名），`dimension` 校验 `product\|institution\|app`，调 `svc_get_securities_aggregation`。**端点尾斜杠遵循 API 契约**（与 `fund-aggregation/` 一致）。
- **无 schema 迁移**：不新增任何列/表（`asset_type` 已存在）。

### 3.2 前端（新增卡片 + 下钻页，克隆 fund-aggregation）
- `frontend/src/views/asset/ledgers/index.vue`：在"场外基金（含E账户）"卡片**并列**新增"场内证券（股票/ETF/可转债）"汇总卡（整卡可点 → `router.push({name:"securities-aggregation"})`），`fetchSecuritiesTotal()` 调 `getSecuritiesAggregation("product")`，失败静默兜底（与现有 `fetchFundTotal` 同范式）。
- 新增下钻页 `frontend/src/views/asset/securities-aggregation/index.vue`：克隆 `fund-aggregation/index.vue` 结构（总市值卡 + 维度 radio + 分组表），仅数据源换为 `getSecuritiesAggregation`。
- 路由 `frontend/src/router/modules/asset.ts`：新增 `securities-aggregation` 路由，`name` 与组件 `defineOptions.name` 一致（keep-alive 要求）。
- `frontend/src/api/ledger.ts`：新增 `SecuritiesAggregationResult` 类型（结构同 `FundAggregationResult`）+ `getSecuritiesAggregation(dimension)`。

### 3.3 与 channel_category（#1136）的关系
- #1132 的 institution 维度用 `ledger.sales_institution_id`（券商机构），**不依赖** `channel_category`；两者正交，无交互。
- 卡片展示文案用既有标签体系，不引入新硬编码。

## 4. 决策（D1~D4，已确认）

- **D1 范围**：`asset_type` 过滤集 = `{etf, bond, stock}`（股票 + ETF + 可转债，即全部场内证券）✅ **已确认**（用户纠正：股票也纳入本期；原"ETF/可转债"为收窄表述，实际含股票）。
- **D2 虚拟账本**：场内证券**不建** `is_aggregation` 虚拟账本，纯 position 级聚合（仿 fund_aggregation）✅ **已确认**（采纳建议）。
- **D3 卡片位置**：与"场外基金"卡片并列于同一资产概览页、点击下钻 ✅ **已确认**。
- **D4 命名**：端点/路由用 `securities-aggregation` ✅ **已确认**。

## 5. 不在本期范围

- `stock`（普通股票）聚合：留待独立评估。
- #1133 聚合视图视觉优化（卡片区分度/观感）：独立 issue，不改本次逻辑。
- 场内证券的"聚合对账"（类似 E账户 `ownership_status` 对账）：本期不做，仅展示聚合市值。

## 6. 验证计划

- 后端：`pytest` 新增 `tests/domains/test_securities_aggregation.py`，覆盖三维度分组 + 金额口径 + 空数据兜底。
- 前端：`pnpm typecheck` 零错误；手动核对卡片与下钻页三维度切换。
- 端到端：用 dev 库既有 股票/ETF/可转债持仓验证聚合总额 = 各账本同标的持仓市值之和。

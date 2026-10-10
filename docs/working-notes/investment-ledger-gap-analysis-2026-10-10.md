# 投资账本能力对齐：我们 vs 同花顺投资账本

> 整理人：AI（ClawBot）· 2026-10-10 · 基于仓库实测盘点，非凭印象
> 触发：用户给出「同花顺投资账本基础功能」清单，要求评估偏差与缺失并拆分
> 方法：两个 code-explorer 分别盘点「账本/盈亏/收益率」与「行情/净值/估值」链路，结论均带文件行号；本文只做综合判定与拆分

> **修订记录（2026-10-10 晚，用户反馈后）**
> §1.5 / §3 关于「盘后预计估值」的结论**已修正**。上一版只盘点了后端、没把前端已有的实时估值链路算进去，误判成「完全没有」。
> 事实是：**盘中/实时估值我们早就有，且是成品**（`useRealtimeQuotes` + `valuationEngine` + 估值开关/状态/横幅，覆盖自选页与多个持仓页）。
> 真缺口不在「能不能估」，而在「**估完不留痕**」——后端不落库，所以收盘后无法定格、进不了账本、没有「预计 → 正式」对照。
> 修正后的判断：**该做**，一期做「收盘后估值快照」，见 §1.5 与 §4 的 K / L / M 卡。

## 0. 一句话结论

**账本主干已经齐了**——持仓/成本/浮动盈亏/已实现盈亏/流水/多账户/收益日历/XIRR 都在跑。

缺口集中在三处：

1. **收益口径的高级层**：TWR（时间加权）、账户 vs 基准、已清仓统计、收益归因 —— 要么完全没有，要么只有表壳子；
2. **数据可靠性底座**：每日资产快照不在调度里且语义不可靠、现金不成闭环、多市场时区/日历缺失；
3. **盘后估值**：前端**已有**成熟的实时/盘中估值链路，但**后端不落库** —— 收盘后无法定格、进不了账本、没有「预计 → 正式」对照。修订后判断：**该做**（见 §1.5、§4 的 K/L/M 卡）。

## 1. 逐条对齐（按你给的九类）

### 1.1 投资账本查询

| 你要的 | 我们的现状 | 判定 |
|---|---|---|
| 持仓数量 / 成本 / 当前市值 | `positions/models.py:25` + `position_service.py`；市值走 `compute_latest_quote`（`watchlist_display.py:321`）| ✅ |
| 浮动盈亏 | `pnl_service.py:131 position_pnl_cents` | ✅ |
| 已实现盈亏 | `transactions/models.py:35 realized_pnl`（卖出结转）；`pnl_service.py:58 compute_sell_realized_cents` | ✅ |
| 累计收益率 | `ledger_service.py:227 get_cumulative_return` | ✅ |
| 账户总资产 / **现金** / 持仓资产 | `ledger_service.py:86 get_overview_stats`；**现金是短板** | ⚠️ |
| 单日 / 单月 / 单年 / 指定区间盈亏 | `GET /api/summary/pnl-calendar/`（`summary/views.py:158`，granularity=day/month/year + 自定义区间）| ✅ |
| 逐品种收益明细 | `position_service.py:1452 build_position_list`、`pnl_service.py:75 realized_pnl_by_position` | ✅ |
| 分账户查询 + 总账户汇总 | `Ledger`（账户）+ `Portfolio`（组合）+ family；`summary_service.py:342 get_account_groups`、`:472 get_ledger_distributions` | ⚠️ 三套层级并存，汇总散在 3 处 |
| 分红 / 配股 / 申赎 / **定投** 记录 | 流水支持 `buy/sell/dividend/dividend_reinvest/deposit/withdraw/split/bond_redeem/tax` | ⚠️ 流水能记，**无定投计划模型**；配股只映射成 dividend |

现金那条的具体问题（三处表达不统一）：

- `Asset.major_category == 'current'` 的余额（`assets/models.py:39`）
- 账户内现金经 `Ledger.linked_cash_ledger_id` 关联（`ledger_service.py:250 get_cash_balance`）
- 持仓维度 `asset_type='cash'`，且被**排除在收益口径外**（`core/asset_types.py:97 EXCLUDED_ASSET_TYPES`）

结果：「账户总资产」里现金的来路不唯一，各页面口径可能不同。

### 1.2 交易记录与账本维护

| 你要的 | 我们的现状 | 判定 |
|---|---|---|
| 买入/卖出、申购/赎回 | `positions/views.py:129 POST /api/positions/`（op_type 白名单 → `dispatch_position_op`）| ✅ |
| 成交价 / 数量 / 日期 / **佣金 / 税费** | `Transaction`：`trade_date`/`quantity`/`price`/`fee`/`amount`/`confirm_date` | ⚠️ **佣金与税费没分离**：只有聚合 `fee`，税费走 `txn_type='tax'` |
| 账单导入（含同花顺）| `importers` 域 + `THS_OP_TYPE_MAP`（`core/constants.py:109`）| ✅ |

### 1.3 投资表现分析

| 你要的 | 我们的现状 | 判定 |
|---|---|---|
| 哪些品种贡献主要收益 / 拖累 | **无归因实现**（grep `贡献`/`attribution` 仅命中注释）| ❌ |
| 已清仓：盈亏 / 持有天数 / **胜率** | `ClearedPosition`（`watchlist/models.py:143`）字段齐全（`realized_pnl`/`realized_pnl_pct`/`holding_days`/`trade_count`/`benchmark_return`），但**全仓零写入方**；清仓即删持仓行（`transactions/models.py:39`）| ❌ **表壳子** |
| 交易频率 / 持仓周期 / 行为特征 | 仅自选页 `smart-prompt-conditions` 在硬算 `holding_days`/`trade_count`（`watchlist/views.py:544`）| ❌ |
| 股票与基金资产配置 | `summary_service.py:389 get_distributions`、`position_aggregation.py:429 aggregate_positions` | ✅ |
| 账户收益 vs 指数 | `Portfolio.benchmark` 只存不算；`IndexDaily` 有数据但没做对齐 | ❌ |

### 1.4 市场与标的数据

| 你要的 | 我们的现状 | 判定 |
|---|---|---|
| A股 / 港股 / 美股 / 基金 / 指数 / 转债行情 | `price_history`（A股/ETF/转债）、`daily_worth`（基金净值）、`index_daily`（指数）、`market_asset_daily`（20 大类资产日频快照，**长历史不落库**）| ⚠️ 港股/美股无独立行情表 |
| 财务指标 / 估值指标 / 技术指标 | 只有指数估值 `index_valuations`（pe / dividend_yield）| ❌ 个股财务与技术指标无 |
| 资金流向 / 涨跌排名 / 筛选 | ❌ | ❌ |
| 新闻 / 公告 / 研报 / 互动 | ❌ | ❌ |
| 基金净值 / 费率 / 交易日 | `daily_worth`、`PurchaseRule`/`RedeemRule`/`FeeRatio`、`core/trading_calendar.py:44` | ✅ |
| 实时行情 | **后端不落库**：`position_price_job.py:13` 明确「只写已确认值，不写盘中估值」；盘中价走前端 `useRealtimeQuotes` | ⚠️ 架构选择（见 §3）|

### 1.5 盘后预计估值（**已修订**）

**修正后的结论：估值能力我们早有（前端成品），缺的是「收盘后定格 + 落库 + 与官方净值对照」。应该做。**

**已有的（前端，成熟度高，被上一版漏掉）**：

| 环节 | 实现 |
|---|---|
| 估值数据源 | `utils/realtimeDataSources.ts`：天天基金 `FundValuationLast` 批量（`GSZ` 估算净值 / `GSZZL` 估算涨跌 / `GZTIME` 估值时间，一次 50 个）、`fundgz` 单只、腾讯行情批量；含缓存 / 超时 / 降级 |
| 估值计算 | `utils/valuationEngine.ts:39 calculateHoldingsValuation` → 逐项市值 / 盈亏 + 汇总（`source: realtime \| static` 标记降级）|
| 接线 | `useRealtimeQuotes`（轮询 / 开关 / 状态）、`useWatchlistValuation`（自选页）、`usePositionValuation`（#1104 持仓「盈亏双线」，覆盖 inventory / 账本持仓 / 组合 / 策略页）|
| UX | `RealtimeEstimateToggle`（开关）、`RealtimeStatusIndicator`（状态灯）、`RealtimeWarningBanner`（异常横幅）、`ESTIMATE_DISCLAIMER`（免责文案）|
| 品类白名单 | `stock`/`etf`/`bond`/`fund` 参与；货基、逆回购明确排除（`usePositionValuation.ts:44`）|

**真缺口（三条）**：

1. **后端不落库，收盘后无法定格** —— `usePositionValuation.ts:16` 明确写「后端**不落库、不维护**预估口径」。后果：估值只在**页面开着的那一刻**存在，用户晚上回来看到的是当下重新抓的值，而不是「收盘时点」的值；
2. **估值进不了账本** —— 收益日历、资产曲线、区间收益全部基于 `positions.current_price`（`position_price` job 回写）与 `daily_worth`，**不含当日预估**。于是官方净值出来前「今天赚了多少」答不出来 —— 而这恰是盘后最想知道的一件事；
3. **没有「预计 → 正式」对照** —— `daily_worth` 走 `INSERT OR IGNORE`（`fund_nav_job.py:152`）**只补不改**；没有预计值独立存储，也没有「官方净值到位后替换并算偏差」的路径。

**为什么「收盘后做」比「盘中做」更值得**：

- 股票侧收盘价已确定 → **不是估算，是确定值**（不必担心上一版说的「精度天花板」）；
- 基金侧官方净值通常当晚 20:00 后才出 → 此时定格估值，**恰好补上账本的这段空窗**；
- 责任边界清晰：估值来源标注为第三方（如天天基金估值），官方净值到位后对照并替换，**不与正式口径混写**。

### 1.6 分账户估值与总收益率口径

| 你要的 | 我们的现状 | 判定 |
|---|---|---|
| 三层：品种 → 账户 → 总账户 | 有：`Position` → `Ledger`（账户，`ledger_service.py`）→ 家族（`summary_service.py`）| ⚠️ 汇总口径分散在多处 |
| **总收益率不能简单平均** | **没有正确实现这块** | ❌ |
| 时间加权收益率（TWR）| **无**（`dietz`/`time_weighted`/`twr` 全仓零命中）| ❌ |
| 资金加权收益率（MWR）| XIRR 即 MWR 的一种（`performance/xirr_engine.py:113`，scope 支持 position/portfolio/symbol/家庭）| ✅ |
| 修正 Dietz | ❌ | ❌ |
| 区间收益率 | `pnl_calendar.py:691`（分母 = 区间前一天净资产）| ✅ |

你第 7 条点出的正是这块：**我们只有资金加权（XIRR），没有时间加权**，所以「不同账户规模不同、不能简单平均」这件事在汇总口径里没有答案。

### 1.7 每日资产快照（你第 9 条「展示」的地基）

`asset_snapshots`（`summary/models.py:12`）与 `pnl_daily_snapshots`（`:89`）两张表都在，但：

- `asset_snapshot` job **不在每日调度内**（`daily_scheduler.py:372` 注释「资产快照按用户手动触发」）；
- 模型 docstring 自认「`snapshot_date` 只是个**标签**……回填等于把今天的值贴到历史日期」（`summary/models.py:94`）。

→ 判定 **⚠️ 地基不可靠**：历史资产曲线与区间收益都会受它牵制。

### 1.8 数据质量

| 场景 | 现状 | 判定 |
|---|---|---|
| 停牌 | 无专门处理（靠 `price_history` 缺口回补 + `pnl_calendar` 向前沿用最近价）| ⚠️ |
| 净值未发布 | 有（`fund_nav_job.py:66` T 日不回填；`pnl_calendar.py:996` 给 no_data / closed）| ✅ |
| 多市场时区 | **无**：全链路统一 `Asia/Shanghai`，交易日历只有 A 股 | ❌ |
| 代码变更 | 无变更追踪机制 | ❌ |
| 幂等 | 有（`import_hash`、快照 `CALIBER_VERSION`、job 的 INSERT OR IGNORE）| ✅ |

## 2. 缺口排序（我眼里的三个最薄弱环节）

1. **「已清仓 / 卖出后」的统计链条是断的** —— 表建好了却没有写入方，胜率/盈亏比/持有期这类账本用户最想看的数字全缺；
2. **收益口径单薄** —— 只有 XIRR，无 TWR / 无基准 / 无归因，导致「这只票到底赚了多少、比大盘好还是差」答不上来；
3. **「账户层」没有统一汇总口径** —— `Ledger`/`Portfolio`/`family` 三套层级并存，汇总散在三处，现金又不成闭环。

## 3. 哪些该做、哪些建议不做

### 该做（账本核心，且多数是修实打实的缺陷）

1. **已清仓统计落地** —— 表都在，只差写入路径；
2. **资产快照每日化 + 修语义** —— 否则历史资产曲线与区间收益都不可信；
3. **TWR + 账户 vs 基准** —— 你第 7 条指的就是这里，且 `IndexDaily` 数据已具备；
4. **收益归因（谁赚谁亏）** —— 纯本地计算，不需要新外部数据；
5. **现金闭环** —— 它牵制「账户总资产」的可信度；
6. **佣金 / 税费分离、定投计划** —— 建模完整性。
7. **收盘后估值快照**（修订：原判「不做」，见 §1.5）—— 当初的三条理由都站不住：
   - **不重造估值**：前端已有估值链路，我们做的只是「**在收盘时点定格并落库**」，不是自己算基金净值；
   - **股票侧是确定值**：收盘价已出，当日持仓盈亏可精确计算，不存在估算误差；
   - **基金侧责任边界清晰**：估值来源标注第三方，官方净值到位后**对照 + 替换 + 记录偏差**，不与正式口径混写。

### 建议不做（或明确排除在一期外）

**8. 个股财务 / 技术指标、资金流、新闻研报** —— 外链已覆盖，自建性价比低且数据源维护成本高。

## 4. 拆分建议（可直接开工的卡）

按「影响正确性 → 影响分析深度 → 影响完整度」排序：

| # | 卡 | 内容与范围 | 依据 | 体量 |
|---|---|---|---|---|
| A | 已清仓统计落地 | 清仓时写 `ClearedPosition`；加只读端点 + 前端列表（累计胜率、盈亏比、平均持有天数）| `watchlist/models.py:143` 表已在、零写入 | 中 |
| B | 资产快照可靠化 | `asset_snapshot` 进每日调度（排在 `position_price` 之后）；修 `snapshot_date` 语义（真快照，或改名说明它只是标签）| `daily_scheduler.py:372`、`summary/models.py:94` | 中 |
| C | TWR + 区间年化 | performance 域加时间加权收益率（按外部资金流切分子区间）+ 年化；与 XIRR 并列并说明差异 | 全仓无 TWR | 中 |
| D | 账户 vs 基准 | 用 `IndexDaily` 把账户/组合净值序列与基准对齐算超额；让 `Portfolio.benchmark` 真正参与计算 | `portfolios/models.py` 字段闲置 | 中 |
| E | 收益归因 | 逐品种对区间收益的贡献（金额 + 占比），支持按账户/组合切分 | 无实现 | 中 |
| F | 现金闭环 | 现金账户余额 + 现金流水（转入/转出/利息），并入总资产与收益口径 | `assets`/`ledgers` 三处表达不统一 | 大（动口径）|
| G | 佣金 / 税费分离 | `Transaction` 拆 `fee` / `tax`；含迁移与导入映射 | 现只有聚合 `fee` | 小-中 |
| H | 定投计划 | 计划模型（周期 / 金额 / 标的）+ 到期生成流水 | 无 | 中 |
| I | 多市场日历 / 时区 | 交易日历按市场分（A股 / 港股 / 美股）；行情时戳带市场与状态 | 全链路 `Asia/Shanghai` | 大 |
| J | 数据时间与状态标注 | 各数据区块统一展示「数据截止时间 + 正式/占位/数据不足」 | 用户第 9 条的真价值部分 | 小 |
| K | **收盘后估值快照** | 收盘后定时任务：按收盘价（场内）+ 估值源（场外）算当日预估盈亏并**落库定格**；账本与收益日历可显示「今日预估」 | §1.5 修订；前端估值链路已就绪 | 中 |
| L | **预估 → 正式对照** | 官方净值到位后替换正式值、记录偏差（估得准不准），历史可回溯 | `daily_worth` 只补不改 | 中 |
| M | 估值状态与来源标注 | 估值数字统一带「估 / 确认」标记 + 数据时间 + 来源（与 J 合并实现）| 已有部分（`ESTIMATE_DISCLAIMER`），需收口 | 小 |

**推荐先做 A + B + J**：体量都不大、且修的是实打实的缺陷（表壳子、地基、可信度）；之后再进 C / D / E 这层分析能力。**K / L / M（收盘后估值）单独立一条线**——它是用户明确要的，且前端底座已就绪，详见 §1.5 与《账本能力 backlog》。

## 5. 与既有定位的关系

`#1969` 期间已确立的定位是：**账本回答「我赚了多少」，深度研究交给专业站（外链）**。本清单里属于「行情终端」的部分（个股财务/技术指标、资金流、新闻研报）与该定位冲突，建议按 §3 明确排除；属于「账本身份」的部分（已清仓、TWR、基准、归因、现金、快照、**收盘后估值**）则正是该补齐的深度。

**「收盘后估值」为什么算账本身份而不是行情终端**：它服务的不是「看行情」，而是「**在官方净值出来前先把今天的账算出来**」——收益日历、资产曲线、当日盈亏都因此补齐。行情阅读交给外链，账本自己的当日结果由我们自己定格。

# fundfof 功能借鉴分析（v3 — 基于源码 model 层复核）（2026-08-03）

> 性质：内部备忘（`docs/working-notes/` 屏蔽出构建，不对外）。
> 复核日期：2026-08-03
> 作者：阿垚（品牌）/ imoyao（技术）讨论稿
> 状态：**源码复核版（已读 `fundmate-main-v2` backend model 层 + frontend 分析页）**
> 参考站：fundfof.com（基金研究/FOF 分析平台，数据驱动，与多倍贝手动记账定位不同）

## 0. 先认错（最重要）

我之前的版本把 **多账户聚合、全交易类型、XIRR+回撤、自选/提醒、手动记账、统一资产模型** 列为"待实现/已规划"，这是**错的**——这些在你们的 model 层**已经存在**。重新读源码后，下面一律以源码事实为准，不再重做已实现项。

---

## 一、源码已经实现的能力（事实，来自 model 层，不再重做）

| 能力 | 源码证据 | 状态 |
|---|---|---|
| 统一资产模型 | `Transaction` / `Position`(asset_type) / `Security`(stock/etf/bond/future/crypto) / `Fund` / `Asset`(非交易资产&负债) / `Ledger` / `Portfolio` | ✅ 已实现 |
| 多账户聚合 | `Ledger`(ledger_type: stock/fund/property/bank/family) + `summary` 域 `get_account_groups` / `get_sankey_data` | ✅ 已实现 |
| 全交易类型 | `PositionService` op_type: buy/sell/dividend/deposit/withdraw；`Transaction` 含 status/entry_status/link_group_id | ✅ 已实现 |
| XIRR 年化收益 | `performance` 域 `calculate_position_xirr` / `calculate_portfolio_xirr(_by_id)`；`XirrResponse` | ✅ 真实计算 |
| 自选 + 异动提醒 + 清仓复盘 | `watchlist` 域：`WatchlistItem`/`Group`/`Tag`/`Alert`/`ClearedPosition`(next_review_date, review_notes) | ✅ 模型层已实现 |
| 基金元数据 + 净值 + 费率 | `funds` 域：`Fund`/`FundCompany`/`Manager`/`DailyWorth`/`MoneyFundDailyWorth`/`FeeRatio` | ✅ 已实现 |
| 证券行情 | `securities` + `price_history`(open/high/low/close/adj_close/volume) | ✅ 已实现 |
| 市场温度 | `temperature` 域：`MarketSingleValue`/`Composite`/`MultiItem`（源：且慢/有知有行/韭圈儿/集思录） | ✅ 模型层已实现（需数据管线填充） |
| 策略标签 / 风格 | `strategy` 域：`StrategyTag`/`PositionStrategyTag` | ✅ 模型层已实现 |
| 手动记账 + 导入 | `Transaction` + `importers` 域(parsers) | ✅ 已实现 |

> 结论：你们的数据底座比 v2 假设**完整得多**。fundfof 的"研究层"（全市场排名/经理/回测/AI选基）本就不该抄；可借鉴的是它的**分析展示层**，且必须只算你们**自己的数据**。

---

## 二、当前实现的真实问题 / 风险（仅在此列，符合"实现有问题才提"）

1. **【演示债】两个分析页是硬编码 mock，不是真功能。**
   `InvestmentAnalysis.vue` 与 `IntelligentAnalysis.vue` 里的数字全是写死：最大回撤 `-8.2%`、夏普 `1.2`、配置建议、收益预测 `¥2,580,000`、月度盈亏 `[1000,2500,-500…]`。未接任何后端 API。
   → 风险：UI 看起来"做完了"，实为空壳，容易误导对外演示或误判进度。

2. **【回撤/波动/Sharpe/相关性 并未真正计算。】**
   后端 `performance` 服务**只有 XIRR**；全仓 grep `drawdown|volatility|sharpe|correlation` 仅在测试 fixture 与 thermometer README 命中，业务代码无实现。即 v2 里我误判"回撤已实现"——**实际没有**。

3. **【多用户隔离未落实。】**
   `Asset.user_id = Column(Integer, default=1)`，无 users 表外键；其他表也未见 row 级隔离。若接 Supabase 真实多用户，存在跨用户数据泄露风险——与你们强调的"数据主权"直接冲突。需确认 Supabase RLS / 应用层隔离是否已兜底。

4. **【市场温度是空模型。】**
   temperature 三表已建，但缺定时采集 jobs（eastmoney/qieman/jisilu 等外部源）+ 入库管线；否则有表无数据，前端无可展示内容。

5. **【持仓成本复权口径待验。】**
   `Position.avg_price`（分）/ `quantity`（0.0001 单位）混用股票/基金/可转债；`dividend` 不改持仓数量，但**配股/拆细**会改变 quantity 与成本，需确认 `PositionService` 在配股场景下 avg_price 复权是否正确。

---

## 三、真正值得从 fundfof 借鉴的"新功能"（仅自有数据，不做全市场研究）

> 排名按 **价值↓ / 难度↑**。全部基于你们已有数据，不引入全市场研究。

### A. 把分析页从 mock 接成真实指标（最高价值）

- **内容**：组合/持仓级 最大回撤、年化波动率、Sharpe、相关性矩阵、真实配置占比、收益对比（我的组合 vs 沪深300 / 中证全债）。
- **数据**：`price_history.adj_close` + `daily_worth`（基金）+ `transactions`（现金流）+ 基准指数行情。
- **难度**：中。后端新增 analytics 服务 ≈ 3–4 人日；前端把两个 mock 页接 API ≈ 1–2 人日。
- **为什么只借"展示层"**：fundfof 的排名/经理/回测/AI选基需全市场数据，你们没有也不该建。

### B. 基金 / 指数 对比功能（中价值）

- fundfof 的 `基金对比` / `指数对比`：多选标的并排看净值曲线、区间涨跌、风险指标。
- **你们现状**：前端 grep `对比|compare` **0 命中**；后端 `funds`/`securities`/`price_history`/`daily_worth` 底层数据齐全。
- **做法**：新增 `/api/analytics/compare` + 对比页（选 2–5 个标的 → 归一化曲线 + 区间收益/波动对比）。难度中 ≈ 2–3 人日，数据依赖低。
- **边界**：只做"自有持仓/关注标的"对比，不做全市场筛选排名。

### C. 清仓复盘页模板化（低新增，高性价比）

- `watchlist` 已有 `ClearedPosition`（realized_pnl / holding_days / benchmark_return / next_review_date / review_notes），但需确认是否有"复盘页"把它展示并支持到期提醒。若无，补轻量复盘页/提醒 ≈ 1 人日。

---

## 四、明确不借鉴（与定位冲突）

- 全市场基金排名 / 筛选、基金经理分析、策略回测、AI 选基、盘中实时估值。
- 理由：依赖全市场数据 + 外部 API，与"手动记账 + 家庭资产"定位不符，会把项目做重（你此前明确反对）。

---

## 五、渐进式落地（避免压垮）

- **P0（先止血）**：A —— 真实指标接入两个 mock 页。
- **P1**：B —— 基金/指数对比。
- **P2**：C —— 清仓复盘页。
- 不碰研究层。

---

## 六、待你确认（决定 P0 优先级）

1. `InvestmentAnalysis.vue` / `IntelligentAnalysis.vue` 是有意为之的**占位演示**，还是**还没接后端**？（决定 A 是否立刻排期）
2. `user_id=1` 的多用户隔离，Supabase RLS 是否已兜底？
3. 市场温度采集 jobs 是否已排期？
4. 配股/拆细场景下 `avg_price` 复权是否正确（问题 5）？

# 资产管理记账能力补齐开发计划（2026-08-30）

> 依据：[`asset-management-gap-analysis-2026-08-30.md`](./asset-management-gap-analysis-2026-08-30.md)（对照真实用户六条需求的 gap 分析，含全部代码锚点）
> 状态：**待评审**，D1~D4 四项决策需先拍板再开工

## 一、为什么这份计划值得做

那位用户提的六条需求不是功能清单，而是一个模型主张：**资产的记账粒度应该由"能不能拿到净值"决定，而不是由产品形态决定。**

三家竞品在这条主张上都结构性做不到——钱往官方 FAQ 承认"依赖手动管理的记账软件"搞不定份额浮动的货基，有知有行官方写明"渠道就是求和的辅助计算器，不要用来记录持仓明细"。它们不是不努力，是「份额 × 净值」单一模型到不了那里。fundmate 的 `position_aggregation` 已经按 symbol 聚合出各账户市值明细（`position_aggregation.py:205-244`），分摊的分母是现成的，只差一个可写市值列和一个分摊服务。这是低成本、高壁垒的一笔投入。

## 二、待拍板的四项决策（阻塞开工）

**D1：计价模型用「双态」还是「打补丁」。**
方案 A（推荐）：给 `Position` 加 `valuation_mode` 枚举（`nav` 份额×净值 / `balance` 直接余额）+ `market_value_override`，市值计算统一走一个分支。方案 B（不推荐）：只加 `market_value_override` 一个列，靠"有值就优先"来判断。
A 的好处是语义自洽、可枚举、后续盈亏口径能跟着模式走；B 会让"这到底是净值型还是余额型"变成隐式约定，三个市值计算点（`position_aggregation.py:51-73`、`summary_service.py:110,291`、`positions/views.py:42`）迟早再次分叉。**结论未定，倾向 A。**

**D2：无净值产品进 `positions` 还是留在 `assets`。**
现在 `assets` 能只录总价但无持仓语义（无流水、不进盈亏），`positions` 有持仓语义但强制净值+份额（`position_service.py:366-371`）。给用户补"投顾产品"这个场景，需要二选一：给 `positions` 开 balance 模式，还是给 `assets` 补流水能力。**倾向前者**——流水、成本、盈亏、XIRR、聚合、分摊全都现成，且不用新建一套并行体系。

**D3：balance 模式的盈亏口径。**
nav 模式是 `(current_price − avg_price) × quantity`。balance 模式份额为 0，得改成"当前余额 − 累计净投入"，净投入从 `transactions` 表按 symbol 累加 `amount`（`transactions/models.py:32`，单位分）。需确认分红/赎回怎么扣减，以及要不要复用 XIRR 的现金流定义（`xirr_engine.py:180-188` 已按 `dividend_cash`/`dividend_reinvest` 区分正/负现金流）。

**D4：无净值产品的聚合入口放哪。**
现有聚合页绑死了品类：`fund_aggregation.py:19` 的 `FUND_ASSET_TYPES=('fund','money_fund')`、`securities_aggregation.py:16` 的 `SECURITIES_ASSET_TYPES=('etf','bond','stock')`，前端对应 `views/asset/funds/index.vue` 与 `views/asset/stocks/index.vue`。投顾/理财归到新大类后进不了这两页，而 ⑥ 的需求入口正是"产品维度下钻抽屉"。要么新增"理财/其他"聚合页，要么把聚合改成品类可配置。**倾向新增一页**（改动小、不动存量）。

## 三、分期计划

### P0 — 止血与低成本补齐（工作量 S）

| ID | 事项 | 涉及文件 | 象限 |
|---|---|---|---|
| P0-1 | **清理前端硬编码假数据** | `views/asset/AssetOverview.vue:391-395,410-422,446-453`、`views/account/components/ProfitTrendChart.vue:20-33`、`views/account/components/AssetDistributionChart.vue:22-36`；`AssetOverview.vue:468` 周期切换是空 `console.log` | **Q1** |
| P0-2 | 补齐资产大类枚举 | `core/constants.py:62-69` `ASSET_CATEGORY_LABELS`、`core/constants.py:18-33` `TYPE_LABELS`；顺带修 `assets/models.py:39-43` 注释里写了 `custom` 但常量表没有的不一致 | Q2 |
| P0-3 | 账户归属家庭成员 | `domains/ledgers/models.py` 加 `owner_user_id`；`domains/families/views.py` 补成员管理 API（现仅 `:43-44` 创建、`:50-58` 列表，前端零调用） | Q2 |

P0-1 单独说明：三处"收益趋势/资产分布"图是硬编码数组，比"功能没做"更伤信任，优先级等同线上缺陷。

### P1 — 余额型持仓（核心差异化，工作量 M~L）

| ID | 事项 | 涉及文件 | 依赖 |
|---|---|---|---|
| P1-1 | `Position` 加 `valuation_mode` + `market_value_override` + `value_override_at`，写迁移脚本（参照 `backend/scripts/migrate_price_units.py`）；加列无需动 `db_factory.py:56-99`，若新建表须登记为 user 域 | `domains/positions/models.py`、`domains/positions/schemas.py:37-47` | D1 |
| P1-2 | balance 模式跳过净值/份额校验的建仓分支 | `services/position_service.py:366-371`（拦截点）、`:378-384`、`:401/:454`（`total_cost/total_qty` 除零）、`:500`、`:530-531`、`:645-654`；前端 `components/QuickEntry/BuyForm.vue:490-499,548,845-846,886-887` | D2, P1-1 |
| P1-3 | **市值口径收口**：三处派生计算抽成公共函数并同时支持 override | `services/position_aggregation.py:51-73`、`services/summary_service.py:110,291`、`domains/positions/views.py:42` | P1-1 |
| P1-4 | 新建 pro-rata 分摊服务与端点 `POST /api/positions/allocate-value/` | 新建 `services/value_allocation_service.py`；复用 `position_aggregation.py:205-244` 的 `sources[]` 作分母；整数分 + 尾差归到占比最大一笔，沿用 `:73` 的 Decimal ROUND_HALF_UP；登记 `domains/positions/views.py` | P1-1, P1-3 |
| P1-5 | 下钻抽屉加"改总价 → 按占比分配"交互 | `components/Aggregation/AggregationProductDetail.vue:43`（`totalYuan` 只读）、`:55-57`（已识别 `multiChannel`）、`:143,:169`（各账户只读展示）；新增 `src/api/` 接口 | P1-4, P1-6 |
| P1-6 | 无净值产品纳入产品维度聚合 | `services/fund_aggregation.py:19`、`services/securities_aggregation.py:16`；`views/asset/funds/index.vue`、`views/asset/stocks/index.vue` | D4 |

资金进出提示可复用现成设施：`domains/utils/views.py:17-36` 的 `GET /api/utils/trading-days/<date>/`，以及 `positions/schemas.py:25` 的 `isAfter15`（15:00 顺延语义现成，只是目前只服务交易创建）。资金进出判定查 `transactions` 即可（`trade_date`/`confirm_date`/`amount`/`link_group_id` 齐备）。

### P2 — 分红送股（对齐竞品基线，工作量 M）

| ID | 事项 | 涉及文件 | 依赖 |
|---|---|---|---|
| P2-1 | 红利再投资接线（修"校验了却不使用"） | `services/importer/orchestrator.py:781-782` 拆分支；`services/position_service.py:700-731` 新增 `process_dividend_reinvest`；`parsers/standard.py:147-153` 已校验 shares+nav；`domains/positions/views.py:232-234` op_type 白名单 | 无 |
| P2-2 | 送股/拆分从孤儿流水改为关联持仓并计入份额 | `orchestrator.py:783-806`（现写 `position_id=None`+`orphan`）、`position_service.py:645-654`（重算未纳入 split）、`domains/transactions/views.py:189`（回滚未纳入） | 无 |
| P2-3 | 新增分红送股抓取 Job | 新建 `services/sync/jobs/dividend_split_job.py`（akshare `fund_dividend` / `stock_history_dividend_detail` / `stock_zh_a_xdxr`）；注册进 `services/sync/orchestrator.py:107-122`。**注意**：9 个现有 Job 无一涉及分红，且无调度器（见 `nav_service.py:36-39` tech-debt），需一併解决触发 | P3-2 |
| P2-4 | 前端分红/送股录入表单 | `views/asset/investment/manual/index.vue:221-229`（现为"功能开发中"占位）；`src/constants/index.ts:97-104` `TXN_TYPE_LABELS` 补 split 与再投资 | P2-1 |

P2-1 是性价比最高的一项：`BusinessType` 里 `DIVIDEND_REINVEST` 枚举早就有（`services/importer/mappings.py:28`），只是执行层把它和 `DIVIDEND_CASH` 合并进了同一分支，`position_service.py:720` 硬编码 `quantity=0`，语义全程丢失。这是纯粹的逻辑缺陷而非能力缺失。

### P3 — 账户维度走势与盈亏（工作量 L，唯一需要新建数据模型）

| ID | 事项 | 涉及文件 |
|---|---|---|
| P3-1 | 快照下沉到账户维度 | `domains/summary/models.py:19-26`（`asset_snapshots` 现只有 `family_id/snapshot_date/total_assets/total_liabilities/net_worth`，**无账户列**，物理上不支持账户维度）；`services/summary_service.py:542-547` 查询签名；需评估给快照加 `ledger_id` 还是新建持仓级日估值表（后者还能补上"历史份额未落库"这个根因） |
| P3-2 | 每日调度器 | 现在快照靠 `views/asset/panorama/index.vue:178` 的 `postSnapshot().catch(() => {})` 惰性触发并吞掉异常；净值同步同样无调度（`services/nav_service.py:36-39` 已登记 tech-debt）。两项一并收口 |
| P3-3 | 盈亏口径拆分（已实现/未实现/浮动） | 现全系统只有 `(current_price − avg_price) × quantity`（`summary_service.py:113-119`、`services/ledger_service.py:157-172`）；成本是移动加权平均（`position_service.py:394-402`），非 FIFO（FIFO 仅用于赎回费预估，`fund_service.py:351,372`） |

P3 依赖 P1：无净值产品的市值要能进快照，balance 模式得先立住。

### P4 — 渠道下透（工作量 S，可随时穿插）

渠道已挂在账户上（`domains/ledgers/models.py:130-135` 的 `sales_institution_id`、`:161-166` 的 `channel_category`、`:148` 的 `frontend_app`），完成度是六条需求里最高的。缺的只是让渠道参与分组筛选与展示——`position_aggregation.py:231-242` 的 `sources[]` 已经带出 `institution_name`/`institution_alias`，前端聚合页加个切片维度即可。象限 Q3。

## 四、风险与纪律

**口径分叉是头号风险。** `summary_service` 用 `current_price`、`position_aggregation` 用 NavService 净值，这两处本就不同源（`position_aggregation.py:87-88` 有历史注释）。新增 override 时若不三处同改，会出现第三个口径。P1-3 的收口是刚需，不是洁癖。

**除零。** balance 模式 `quantity` 为 0，`position_service.py:401/:454` 的 `total_cost / total_qty`、`:645-654` 的重算逻辑都要防。

**数据域红线。** 绝不能把投顾产品总价写回 `daily_worth`（market 域）——那是 user 域写 market 域，撞 `core/db_factory.py:53-55` 边界先例。`position_aggregation.py:137-143` 已示范"跨域读可以、写不行"。

**测试基线。** `backend/tests/domains/test_positions.py` 全部用例都成对提供 `quantity` + `avg_price`，反例只测"卖出缺 position_id / 超卖"。新增 balance 分支必须补两类用例：只传 `amount` 应成功、缺 `avg_price` 在 nav 模式下应报错。跑测试一律 `pdm run pytest -p no:xdist`（单进程，防 OOM）。

## 五、原子 Issue 草案

可直接拆为 GitHub issue，每条遵守"一个 issue 只承载一件事"：

1. `fix(frontend): 清理资产总览/账户页硬编码假图表数据` — Q1 — 验收：三处图表接真实接口或下线，周期切换回调有真实行为
2. `feat(backend): 补齐资产大类枚举（银行理财/投顾/信托/私募）` — Q2 — 验收：新大类可录入、可展示；`assets/models.py` 注释与常量表一致
3. `feat(ledger): 账户支持归属家庭成员 + 成员管理 API` — Q2 — 验收：`Ledger.owner_user_id` 可写，可按成员筛选持仓
4. `feat(positions): 引入 valuation_mode 双态计价模型与可写市值` — Q1 — 依赖 D1 — 验收：balance 模式建仓不填净值份额成功；三处市值计算统一走收口函数
5. `feat(positions): 产品维度按占比批量更新持仓总价` — Q1 — 验收：改一次总价，`Σ(各账户分配值) == 总价`（整数分、尾差归集），涉及资金进出时提示下一开盘日
6. `feat(frontend): 聚合下钻抽屉支持编辑总价并按占比预览分配` — Q1 — 依赖 5、D4
7. `fix(dividend): 红利再投资接线（不再降级为现金分红）` — Q2 — 验收：导入 `DIVIDEND_REINVEST` 后持仓份额增加、类型不丢
8. `fix(split): 送股/拆分关联持仓并计入份额` — Q2 — 验收：不再产生"需手动关联持仓"孤儿流水
9. `feat(sync): 新增分红送股抓取 Job 与调度器` — Q2 — 依赖调度器 — 验收：akshare 分红接口调通并落库
10. `feat(frontend): 分红/送股手动录入表单` — Q2 — 验收："功能开发中"占位消失
11. `feat(summary): 账户维度资产快照与走势` — Q2 — 依赖 4 — 验收：`GET /summary/snapshots/` 支持 `ledger_id`
12. `feat(backend): 每日调度器（快照 + 净值同步）` — Q2 — 验收：不再依赖前端惰性触发
13. `feat(performance): 盈亏口径拆分（已实现/未实现/浮动）` — Q2
14. `feat(aggregation): 聚合页支持按购买渠道切片` — Q3

## 六、建议推进顺序

先拍板 D1~D4（半天内可定），然后 P0-1 与 P0-2 立即开工（都不阻塞），P1 紧随其后——它是唯一能同时绕开三家竞品的路径。P2-1 可以提前插队，那是纯逻辑缺陷修复、改动最小、竞品已交付的基线能力。P3 排最后，它是唯一需要新建数据模型和调度器的部分，且要等 P1 立住才能算准无净值产品的市值。

# 多多贝（fundmate）对照真实用户需求的资产记账能力 Gap 分析报告

## 执行摘要

这份报告把一位资深用户提出的六条硬需求，逐条对齐到 fundmate 现有代码，得出的结论是：**产品的「壳」已经搭起来了（多账户、渠道、持仓聚合、XIRR、产品维度聚合抽屉），但用户真正痛的三件事——投顾/银行理财这类无净值产品的记账与更新、账户维度的走势与盈亏、分红送股自动化——基本都还停在枚举设计阶段，执行层没有接线。**

其中最有战略价值的一条发现是：用户提出的需求 ⑥（产品维度改一次总价、按占比自动分配到各账户），恰恰是三款竞品共同的空白区。钱往官方 FAQ 亲口承认"依赖手动管理的记账软件"搞不定份额随消费浮动的货基，只建议"放入现金类账户、定期更新余额"；有知有行官方更是直接写明"渠道就是一个求和的辅助计算器，但不要用来记录持仓明细"。**这三家不是不做，是它们的「份额 × 净值」数据模型结构性做不到。** fundmate 的 `position_aggregation` 已经按 symbol 聚合出了各账户市值明细（分母现成），只差一个可写市值列和一个分摊服务——这是一条低成本、高壁垒的差异化路径。

另外必须优先处理一个信誉风险：前端 `AssetOverview.vue`、`ProfitTrendChart.vue`、`AssetDistributionChart.vue` 三处「收益趋势/资产分布」图目前是**硬编码假数据**，周期切换按钮是空的 `console.log`。这比"功能没做"更危险。

## 一、背景与判定方法

用户是从"几乎用遍市场上记账和资产类 App"的资深用户视角提出的诉求，基线竞品是同花顺「投资账本」（只支持股票基金、自定义程度不够）、「有知有行」（总值跟踪好但无明细、无法按成员更新持仓）、「钱往」（明细清爽但自定义资产必须录净值+份额、分红送股自动化不全）。用户明确拒绝"收支记账 + 资产记账"二合一，对价格敏感。

判定方法上，本报告所有"已实现/未实现"结论均落到 fundmate 代码的具体文件与行号，不做主观评估；竞品结论来自官网、App Store 页面、官方 FAQ 与版本日志，并对微信公众号检索做了补充（检索效果见"局限性"一节）。代码证据基于 2026-08-30 的 `feat/road-not-taken-revive` 分支工作区状态。

一个术语前提：fundmate 的"账户"在数据模型上是 **`Ledger`**（表 `ledgers`，域目录 `backend/app/domains/ledgers/`），不是独立的 accounts 域。下文统一沿用。

## 二、六条需求对照总览

| 需求 | 判定 | 一句话现状 |
|---|---|---|
| ① 自定义资产免净值/份额 | **部分实现，核心痛点未解决** | 静态资产 `Asset` 只录总价已实现，但无持仓语义、无理财/投顾大类；可交易持仓 `Position` 被 `position_service.py:369/371` 强制要求份额+净值，投顾产品根本录不进去 |
| ② 多账户区分家庭成员 | **部分实现** | 多账户无上限已支持；但账户只有 `family_id`，**没有成员归属列**，只能靠账户名区分人 |
| ③ 购买渠道 | **已实现（完成度最高）** | `sales_institutions`（中基协 AMAC 名录）+ `channel_category` + `frontend_app` 三层，挂在账户上 |
| ④ 账户总值走势与盈亏走势 | **未实现** | 快照表 `asset_snapshots` 只有家庭级三值、无 `ledger_id`；无持仓级历史市值表，账户历史市值**物理上算不出来**；前端走势图是硬编码 mock |
| ⑤ 分红送股自动化 + 再投资选择 | **未实现（枚举已设计，执行层没接线）** | 导入层枚举含 `DIVIDEND_REINVEST`/`SPLIT`，但被合并走同一分支，再投资语义全程丢失、送股只留孤儿流水；9 个同步 Job 无一涉及分红送股 |
| ⑥ 按占比批量更新总价 | **未实现，但基础最好** | 无 pro-rata 机制、市值不可独立写入；但 `position_aggregation` 的 `sources[]` 已按账户给出市值明细，分母现成，只差写回 |

## 三、逐条 Gap 分析

### 需求①：自定义资产免净值、免份额

fundmate 实际上是两套并行的记账模型，而用户的痛点正好卡在两套模型的接缝处。

静态资产 `Asset`（`backend/app/domains/assets/models.py:23-81`）当前只有一个 `amount`（整数分）标量，**没有任何净值与份额字段**，Schema 层也只要求 `major_category` / `name` / `amount`（`assets/schemas.py:17-20`），前端表单 `AssetEntry.vue:262-280` 同样只校验这三项。也就是说，"只录总价"这条路对静态资产是通的。

问题在于静态资产**没有持仓语义**：它不进 `positions` 表，没有买入/加仓/赎回流水，无法参与成本计算与盈亏统计，本质上是一个死的金额快照。更关键的是大类枚举覆盖不足——`backend/app/core/constants.py:62-69` 的 `ASSET_CATEGORY_LABELS` 只有 `cash / fixed / investment / receivable / liability / insurance` 六项，**没有银行理财、投顾、信托、私募、理财型保险**。`assets/models.py:39-43` 的注释里提到了 `custom(自定义)`，但常量表里根本不存在这个值，属于注释与实现不一致。

可交易持仓这条链则是硬性的"净值 × 份额"。虽然 `positions/schemas.py:15-16,27` 把 `quantity`、`avg_price`、`amount` 都声明为 Optional，看似宽松，但服务层直接拦截：`backend/app/services/position_service.py:366-371` 中 `if qty <= 0: raise ValueError('数量必须大于 0')`、`if price <= 0: raise ValueError('价格必须大于 0')`，紧接着 `:378-384` 还有一道 `SBException(400, field='avg_price')` 重复校验。而 `process_buy_or_deposit` 全程**从未读取 `data['amount']`**，流水金额反而是由 `:500` `Money.multiply_price_quantity(price_units, qty_units)` 倒算出来的；`:401/:454` 的合并均价逻辑按 `total_cost / total_qty` 计算，份额为 0 会直接除零。卖出链更严格，`:530-531` 直接取 `data['quantity']` / `data['avg_price']`，缺失即 KeyError。前端 `BuyForm.vue:490-499` 同样把 `shares` 与 `price` 设为 required，且 `:548` 的联动公式是 `form.shares = (newVal - fee) / form.price`——**净值在交互上就是必填项**。

结论很直接：用户手里的投顾产品，走 `positions` 录不进去（要净值），走 `assets` 能录但只是一笔死钱（无法记流水、无法按占比分配、无法算盈亏）。这正是用户抱怨钱往的那个问题，fundmate 目前没有解决它。

唯一存在的 amount 分支是 `_create_orphan_transaction`（`position_service.py:179`），但它只服务 `money_fund` / `reverse_repo` 这类现金管理品，且这些类型在 `:341-343` 直接 `return None`，不建持仓。

### 需求②：多账户与家庭成员归属

多账户本身是支持的，而且没有数量上限：`ledgers/views.py:437` 用 `db.query(Ledger).filter(Ledger.family_id == get_family_id())` 拉取，账户模型还带了 `ledger_type`、`channel_category`、`sales_institution_id`、`linked_cash_ledger_id`、`is_aggregation`（E账户隐藏）、`display_order`、`is_active`（归档）等相当完整的字段设计。

**缺口在成员归属。** `Ledger` 继承 `FamilyScopedMixin`（`backend/app/core/database.py:54-68`），只有 `family_id` 一列；类定义（`ledgers/models.py:14`）混入 `PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin`，没有 `owner` / `member` / `user_id`。在 `domains/ledgers/views.py` 检索 `owner|member_id|user_id|current_user.id` 是 0 命中。`positions`（`positions/models.py:20-52`）同样如此；`assets` 有个 `user_id`（`assets/models.py:27`）但 `default=1`，形同摆设。

家庭与成员侧的建模也很薄：`Family` 模型（`families/models.py:13-16`）除了主键和时间戳，**只有 `name` 一个业务字段**；成员关系就是 `User.family_id` 外键，角色只有 `admin / member / viewer`（`users/models.py:15-22`）——这是权限角色，不是资产归属维度。API 上只有 `POST /api/families/`（创建时创建者自动变 admin，`families/views.py:43-44`）和 `GET /api/families/<id>/members/`（`:50-58`，仅 admin 可见），**没有成员增删改、邀请、改角色的接口**；前端全量检索 `/api/families`、`createFamily`，除 `api/family.ts` 自身的定义外**没有任何视图调用**。

也就是说，用户想"用账户维度区分不同家庭成员"，现在只能靠给账户起名（"老婆的招行"）这种土办法，系统层面无法按人切片、无法按人汇总、无法按人看走势。考虑到 fundmate 主打"家庭资产管理"，这是定位层面的缺口，而不仅仅是功能缺失。

### 需求③：购买渠道

这是本次调研中完成度最高的一项。存在独立的权威名录表 `SalesInstitution`（`backend/app/domains/positions/models.py:166-190`，`org_name` unique，来自中基协 AMAC 公示数据），账户通过 `ledger.sales_institution_id` 外键关联（`ledgers/models.py:130-135`）。在此之上还有两个正交维度：`channel_category`（`ledgers/constants.py:41`，取值为 `bank / securities / fund_platform / insurance / futures / other`）和 `frontend_app`（`ledgers/models.py:148`，`tonghuashun / eastmoney / self / other`，即"交易前端"标签）。

严格说还有一处可打磨：渠道是挂在**账户**上的，而用户描述里"各账户、各渠道的不同维度"暗示渠道可能与持仓相关（同一产品分在支付宝和且慢两个渠道买）。不过把渠道作为账户属性是主流做法（同花顺、钱往都这么做），且能覆盖 90% 场景，优先级可以放低。真正需要补的是：让渠道字段参与**分组筛选与展示**，目前 `position_aggregation` 只在 `sources[]` 里带出 `institution_name / institution_alias`（`position_aggregation.py:231-242`），前端聚合页没有按渠道切片的能力。

### 需求④：账户总值走势与盈亏走势

这条是缺口最大的，而且不只是"没做接口"，是"数据算不出来"。

先看已有的：`asset_snapshots` 表（`backend/app/domains/summary/models.py:19-26`）只有 `family_id / snapshot_date / total_assets / total_liabilities / net_worth` 五列，**物理上没有账户列**；查询签名是 `(db, family_id, start_date, end_date)`（`summary_service.py:542-547`）。所以 `GET /api/summary/snapshots/`（唯一真实的家庭总值走势数据源）天然不支持账户维度。全系统唯一支持 `ledger_id` 的日序列端点是 `GET /api/performance/money-fund-income/`（`performance/views.py:52`），且品类限定货币基金。

再看为什么算不出来：系统**没有持仓级的历史份额/市值表**。`price_history`（`price_history/models.py:15-38`）是证券日线，`daily_worth`（`funds/models.py:112-120`）是基金净值，都没有"某账户某日持有多少份"。要算账户在某一天的市值，需要"该日持仓份额 × 该日净值"，份额历史未落库，所以账户级历史市值不是实时算得慢，而是**根本无从计算**。

补一刀的是调度缺失：快照写入靠前端页面 mount 时惰性触发（`panorama/index.vue:178` 的 `postSnapshot().catch(() => {})`，错误被吞掉），没有 cron 或任何后台调度，意味着用户不打开全景页就没有历史数据，历史序列必然稀疏。净值同步同样如此——`nav_service.py:36-39` 明确登记为 tech-debt："已实现并注册，但无任何调度器触发，库内净值目前只能靠手动执行更新"。

盈亏口径上，全系统只有一种算法：`(current_price − avg_price) × quantity`（`summary_service.py:113-119`、`ledger_service.py:157-172`），**没有已实现 / 未实现 / 浮动盈亏的拆分**。唯一的 `realized_pnl` 字段在自选股表（`watchlist/models.py:122`），与持仓无关。成本法是移动加权平均（`position_service.py:394-402`），明确不是 FIFO（FIFO 只用于赎回费预估，`fund_service.py:351,372`）。XIRR 倒是实现了且比较扎实：`services/performance/xirr_engine.py:111-149`，优先 `pyxirr`、失败降级为多初值牛顿-拉夫逊（`:45-82`，初值序列 `[0.1, -0.1, 0.5, -0.5, 1.0, -1.0]`），ACT/365，分红按 `DIVIDEND_CASH` 正现金流 / `DIVIDEND_REINVEST` 负现金流计入（`:180-188`）。

最后是一个必须立刻处理的问题。前端三处图表是假数据：`AssetOverview.vue:391-395`（分布饼图硬编码股票36.5/基金28.9）、`:410-422`（累计收益数组 `[120,190,170,220,280,250,310]`）、`:446-453`（风险热力图）；`ProfitTrendChart.vue:23-27`（`[65,59,80,81,56,55]`，X 轴是"一月"到"六月"）；`AssetDistributionChart.vue:22-36`。而 `:468` 的"切换收益周期"回调只有一句 `console.log("切换收益周期:", period)`。真实的图表只有 `Charts/SankeyChart.vue`、`AssetAllocationDonut.vue`（接 `/summary/sankey/`、`/summary/distributions/`）和 `panorama/index.vue`。用户一旦发现有数据的地方是假的，信任成本远高于"这功能还没做"。

### 需求⑤：分红送股自动化与再投资选择

系统里有两套交易类型定义，且不一致。数据库层（`transactions/models.py:26`）`txn_type` 是裸字符串 `String(20)`，无 enum 约束；标签表 `OP_TYPE_LABEL`（`core/constants.py:134-144`）有 9 个值（`buy/sell/dividend/deposit/withdraw/split/bond_redeem/tax/other`），**没有 `dividend_reinvest`**。导入层的 `BusinessType`（`services/importer/mappings.py:16-34`）反而是完整的，含 `DIVIDEND_CASH`、`DIVIDEND_REINVEST`、`SPLIT`，标准模板与同花顺映射也都识别（`:55-73`、`:89-97`，如"送股→split"、"红利入账→dividend_cash"）。

**分红再投资语义全程丢失。** 这条链路的决定性证据是：`orchestrator.py:781-782` 把 `DIVIDEND_CASH` 与 `DIVIDEND_REINVEST` 合并进同一个分支，都调 `PositionService.process_orphan_dividend`；而 `position_service.py:711-731` 硬编码 `txn_type='dividend'`、`quantity=0`、`price=0`、`notes='现金分红'`。更微妙的是，解析器 `parsers/standard.py:147-153` 明明为红利再投资校验了 `shares` + `nav`（报错文案"红利再投资必须提供份额/净值"），但传下去的 `quantity`/`nav` 在 `process_dividend` 里被 `quantity=0` 硬覆盖——**校验了却不使用**。结果是：用户导入一笔"红利再投资"，系统记成一笔普通现金分红，不增加持仓份额，语义永久丢失。后端手动记账 API 也只认 `op_type == 'dividend'` 一种（`positions/views.py:232-234`），传 `dividend_reinvest` 会被 `:245` 判为"不支持的操作类型"。

**送股/拆分只留孤儿流水。** `orchestrator.py:783-806` 创建的是 `position_id=None`、`entry_status='orphan'` 的孤立流水，notes 里明明白白写着"转股入账（需手动关联持仓）"。`position_service.py` 里根本没有 split 处理方法，`trade_rules.py` 也无命中；重算逻辑 `position_service.py:645-654` 只累加 `buy/deposit/sell/withdraw`，**split 份额不计入**；删除流水时 `:189` 的回滚也把 split/dividend 排除在外。前端则靠 `OrphanCleanupDialogs.vue` 让用户手工认领。

**自动化数据源完全缺失。** `services/sync/orchestrator.py:107-122` 注册的 9 个 Job 是 `stock_list / fund_list / fund_detail_enrich / fund_manager / fund_type / fund_nav / price_history / temperature / amac_institution`，无一涉及分红送股。akshare 适配器调用的全部接口是 `stock_zh_a_daily`、`stock_info_a_code_name`、`stock_zh_a_spot_em`、`fund_name_em`、`fund_manager_em`、`fund_info_ths`，**未调用 `fund_dividend`、`stock_history_dividend_detail`、`fund_split`、`stock_zh_a_xdxr` 中任何一个**。`tools/` 目录下同样没有。目前唯一的"自动化"路径是券商 CSV 文件导入，不是网络抓取。

前端录入入口也没开：`views/asset/investment/manual/index.vue:131-163` 定义了股票 `buy/sell/dividend` 与基金 `subscribe/redeem/dividend_reinvest/convert/drip` 的操作组，但表单渲染只有 `BuyForm` 与 `SellForm` 两个分支，其余全部落入 `:221-229` 的 `v-else` 占位块，显示"{{ getFundOpLabel(fundOpType) }} 功能开发中"。也就是说用户选"现金分红"或"红利再投"后**没有任何表单**。

对照竞品，同花顺投资账本官方 FAQ 写明基金分红**在分红到账日自动生成分红流水**、货基默认红利再投、其他默认现金红利且记录可修改。这是竞品已经交付的基线能力，fundmate 在这一项上是落后的。

### 需求⑥：按占比批量更新总价

这是用户最有价值、也最能形成差异化的一条。先说坏消息：**pro-rata 机制完全不存在**。检索 `pro_rata|prorate|allocate|分配|分摊|占比|ratio|weight|batch_update|批量更新|sync_value|rebalance|distribute`，后端零命中业务实现（命中的全是无关的货基展示比例、温度计成交额占比、迁移脚本诊断）。

更根本的障碍是：**市值不可独立写入**。`positions` 表没有 `market_value` 列，市值在所有地方都是 `price × quantity` 的实时派生量——聚合口径在 `position_aggregation.py:51-73`（`_position_market_value_cents`，基金走 NavService 净值、否则回退 `current_price`），汇总口径在 `summary_service.py:110,291`，明细口径在 `positions/views.py:42`。唯一带 `market_value` 列的物理表是 `PositionImportMeta`（`positions/models.py:132`），但那是导入快照溯源字段，不参与任何计算。`PositionUpdate` schema（`positions/schemas.py:37-47`）也没有市值字段。这意味着现在想"把某账户市值改成 2.04 万"，只能令 `current_price = 20400 / 份额`，份额极小或为 0 时除法爆炸或精度失真。

好消息是**基础设施几乎全齐了**。`position_aggregation.py:205-244` 的 product 分组已经以 `symbol` 为 key 聚合出了产品总市值与 `sources[]` 数组，`sources` 每项都带 `ledger_id / ledger_name / institution_name / market_value_cents / quantity / nav_yuan`（`:231-242`）——**占比的分母是现成的，只是没人写回**。跨账户持同一产品靠 `Position.symbol` 表达，配合 `positions/models.py:73` 的 `UniqueConstraint('ledger_id','symbol')`（同账户内 symbol 唯一、跨账户可重复），数据基础正是用户描述的场景。

数据域上没有阻碍，反而有明确边界。查 `backend/app/core/db_factory.py:56-99`：`positions / assets / transactions / ledgers / position_import_meta` 属 **user 域**，`daily_worth / price_history / securities / funds` 属 **market 域**。分摊只碰 `positions` + `transactions`，纯 user 域，无需跨域 JOIN。**但绝不能把投顾产品的总价写回 `daily_worth`**——那是 user 域写 market 域，撞 `:53-55` 的边界先例。`position_aggregation.py:137-143` 已经在聚合里直接查 `DailyWorth`（跨域读），说明"读可以、写不行"。

其他配套也齐：资金进出记在 `transactions` 表，`trade_date`（T 日）、`confirm_date`（确认日）、`amount`（分）、`fee`、`quantity`、`price`、`link_group_id`（转入/转出配对）一应俱全（`transactions/models.py:22-38`），判断"本次是否涉及资金进出"只需要按 symbol 查区间内有无记录。"下一个开盘日"的基础设施也已存在：`domains/utils/views.py:17-36` 的 `GET /api/utils/trading-days/<date>/`，以及 `positions/schemas.py:25` 的 `isAfter15`（15:00 后净值日顺延的既有语义，只是目前只服务交易创建）。

前端入口只差一层窗户纸：`components/Aggregation/AggregationProductDetail.vue` 的聚合详情抽屉，`:43` 的 `totalYuan` 是只读总价，`:55-57` 已经识别出 `multiChannel = sources.length > 1`，`:143/:169` 遍历渲染各账户金额——**把只读展示改成可编辑输入，就是用户描述的那个交互**。

落地需要改动的文件清单：在 `positions/models.py` 加 `market_value_override`（Integer 分，nullable）与 `value_override_at`；新建 `backend/app/services/value_allocation_service.py` 实现 `allocate_total()`（按 `src.market_value_cents / Σ` 求占比、`int(round(total × ratio))`、尾差补到占比最大的一笔保证 `Σ == total`，沿用 `position_aggregation.py:73` 的 Decimal ROUND_HALF_UP）；在 `position_aggregation.py:51-73` 与 `summary_service.py:110,291` 的市值计算处同时加 override 优先分支（**两处必须同步，否则第三个口径出现**）；在 `positions/views.py` 加 `POST /api/positions/allocate-value/`；前端在 `AggregationProductDetail.vue` 加编辑与保存事件。注意 `views.py:295-298` 的换算分支只能套价格/份额类字段，`market_value_override` 已是"分"，不要误套 `Money.yuan_to_price_units`。

## 四、竞品对照与赛道判断

同花顺「投资账本」完全免费、无内购（FoxData 数据，3.6 万评分 4.8），定位是同花顺生态的引流工具。它的杀手锏是**自动化**：券商持仓同步、截图智能识别支付宝/天天基金/腾讯理财通、基金分红在到账日自动生成流水（货基默认红利再投、其他默认现金红利、记录可修改）、定投每周期确认日自动记录。弱点正如用户所说，自定义非股基资产能力存疑，且 App Store 评论里有"更新之后很多原有功能都不能用了"的抱怨。

「有知有行」的边界是**官方主动选择**的。其《记账使用指南》（2023-02-23）给的四步法是建账户→记初始市值→记转入转出→定期更新资产，并明确写道"**渠道就是一个求和的辅助计算器，但不要用来记录持仓明细**"。它的账户维度是"目标/用途"（长赢计划、子女教育金）而非人或平台。这条官方表述非常关键：它说明"总值好、无明细"不是缺陷而是定位，fundmate 不必在这条战线上与它正面竞争，反而应该把"有明细且能自动化更新"作为对立面。另外其用户对"基金分红和投顾费收取应该记为转入还是转出"的提问**未见官方答复**，说明投顾费的记账口径是行业性真空。

「钱往」（杭州铂玲科技）是三家里最贴近用户需求的，也是信息最有价值的一家。定价是免费+内购：铂金会员 ¥12/月、¥28/季、¥88/年、¥328 终身，官方承诺"价格保护、永不降价、从不促销"，评分 4.7（328 个评分），iOS/Android/鸿蒙/Mac 多端同步、权益通用。它的自定义资产自 v1.2.0（2025-04-25）起支持添加交易记录、摊薄/平均成本价切换、价格趋势图，v1.2.8 起"持仓、价格支持小数点后 8 位"——这些细节都指向**「价格 × 份额」模型且价格需手工维护**，与用户的抱怨吻合（不过"是否强制录入净值+份额"未检索到官方明文，属推断）。

钱往官方 FAQ 里两条自白对 fundmate 最有价值。其一，**不支持货币基金自动计息**，理由是"货基每日计息依赖准确份额，而余额宝类份额随消费变动，对于依赖手动管理的记账软件来说管理难度大大的提升……建议放入现金类或储蓄类账户管理，定期更新余额"。其二，**不支持虚拟货币**（大陆合规），建议通过自定义资产手动管理。第一条几乎是整个"份额 × 净值"流派对净值型理财/投顾产品的**通病自白**——用户抱怨的不是钱往不努力，是这个模型结构性做不到。而用户提的"只录总价 + 按占比分配"恰恰绕开了份额，是另一个模型。

赛道上还有两个信号值得注意：App Store 相似推荐位里「金橘记账」主打"多人记账"，说明**多成员是稀缺供给**；「Aseta」主打"快照式净资产追踪、无需逐笔记录"，与有知有行同属"放弃明细"流派。而高端用户在工具与自制 Excel 之间反复横跳（知乎 2024-12 有用户"每周用 Excel 记投资账"后去调研有知有行；2022 年有人"从有知有行账本到定制 Excel 表格"），说明**明细派用户的最终归宿往往是不堪重负后退回表格**——谁能把明细的维护成本压下来，谁就能接住这批人。

## 五、优先级与落地路线

按"用户痛点强度 × 实现成本"排序，建议分三批推进。

第一批是高差异化且成本可控的两件事。**其一是需求 ⑥ + ① 的组合**，这是 fundmate 唯一能同时绕开三家竞品的路径：先在 `core/constants.py:62-69` 补齐资产大类（银行理财、投顾、信托、私募、理财型保险），再在 `positions` 加 `market_value_override` 列并新建 `value_allocation_service.py`，最后在 `AggregationProductDetail.vue` 抽屉加编辑入口。改动面约 7 个文件，且 `sources[]` 分母现成、跨域无阻碍，是投入产出比最高的一笔。**其二是修掉前端假数据**——`AssetOverview.vue`、`ProfitTrendChart.vue`、`AssetDistributionChart.vue` 三处硬编码图表要么接真实接口，要么暂时下线，周期切换的空 `console.log` 必须处理。这是信誉问题，优先级等同功能缺陷。

第二批是补齐竞品已有的基线能力。**需求 ⑤ 分红送股**分三步：先把 `orchestrator.py:781` 的 `DIVIDEND_REINVEST` 拆成独立分支、新增 `process_dividend_reinvest`（按 `shares` 加仓 + 记分红流水），这是最小改动且能立刻修复"校验了却不使用"的逻辑矛盾；再把 `:783` 的 split 改为关联持仓并触发 `recompute_position_from_transactions`，让送股真正增加份额；最后新增 `sync/jobs/dividend_split_job.py` 接入 `ak.fund_dividend` / `ak.stock_history_dividend_detail`。前端 `manual/index.vue:221` 补一个 DividendForm 即可开通手动入口。**需求 ② 的成员归属**成本最低——给 `Ledger` 加一列 `owner_user_id`、补 member 维度的筛选参数，但它撑起的是"家庭"这个核心定位，建议与第一批并行。

第三批是需求 ④ 的账户维度走势，这是最重的一块，也是唯一需要新建数据模型的：要么给 `asset_snapshots` 加 `ledger_id` 并改为按账户写快照，要么新建持仓级日估值表；同时必须补一个每日调度器（顺带解决 `nav_service.py:36-39` 登记的净值同步无调度 tech-debt），并拆分已实现/未实现盈亏口径。建议在前两批上线后启动。

需求 ③ 的渠道能力已基本满足，只需在聚合页补上按渠道切片，可随时穿插。

最后一条产品侧建议：钱往已经支持导入一木/有鱼/iCost/图图/鲨鱼记账五种第三方模板，说明**导入能力是用户切换工具的硬门槛**。这位用户明确说过自己买过 iCost、图图记账，如果 fundmate 能提供从钱往、同花顺投资账本、有知有行及 Excel 的一键迁移，获客阻力会小很多。

## 六、结论

这位用户的需求不是零散功能清单，而是一个连贯的模型主张：**资产的记账粒度应该由"能不能拿到净值"决定，而不是由产品形态决定。** 有净值的走份额模型，无净值的走余额模型，两者都要能记流水、算盈亏、按占比更新。fundmate 目前只实现了前者，而用户抱怨的三款竞品也只实现了前者。

好消息是 fundmate 的底盘比这三家都更适合接住这个主张：`position_aggregation` 已经按产品聚合出了各账户市值明细（分摊的分母现成），数据域划分让分摊只在 user 域内闭环（无跨域阻碍），`transactions` 表的日期与金额字段足以支撑资金进出判定，交易日接口与 15:00 顺延语义也已就绪。缺的是"市值可独立写入"这一个字段，以及把它接进聚合与汇总口径的纪律（两处必须同时改，否则历史上 `summary_service` 用 `current_price`、`position_aggregation` 用 NavService 净值这种口径分叉会再添一例）。

需要清醒的是，产品的门面目前有瑕疵：走势图是假数据、分红与红利再投的前端入口是"功能开发中"占位、送股只留待认领的孤儿流水。这些比"功能没做"更伤信任，建议在推进新能力的同时一并清理。

## 七、局限性

本报告的代码证据基于 2026-08-30 的 `feat/road-not-taken-revive` 分支工作区快照，该分支存在未提交改动（涉及 `watchlist`、`funds` 模型与多个 sync Job），若分支后续变动，个别行号需要复核。

竞品信息方面，微信公众号检索渠道在本次执行中效果不佳：搜狗微信搜索对"净值型理财 记账""钱往 记账"等长尾关键词返回空结果，对"家庭资产 记账"返回的多为 2017-2024 年的陈旧文章（时间筛选对冷门词会补充旧文凑数），仅获得两条有价值的信号（公众号「也谈钱」2023-12-05《为了这个功能，我把所有投资账本都搬家了》；「明月兮」2024-01-11《家庭财务记账·资产负债表》谈及有知有行家庭资产记账体验）。此外知乎专栏返回 403、雪球页面加密，"MoneyWiz / Notion / 飞书模板在 2024-2026 年的中文可靠评测"未检索到。

有一项关键事实未能取得官方明文：钱往的自定义资产"是否强制录入净值和份额"。本报告的判断基于其版本日志中"持仓、价格支持小数点后 8 位""价格趋势图"等间接证据推断，用户原话是更直接的来源，但二者均非官方表述，建议以实测为准。

## 参考来源

1. [有知有行记账使用指南（官方，2023-02-23，"渠道就是求和的辅助计算器"出处）](https://youzhiyouxing.cn/materials/1408)
2. [有知有行账本（官方）](https://youzhiyouxing.cn/guides/invest/abook)
3. [钱往 常见问题（货基不支持自动计息、虚拟货币、会员、长期运营）](https://www.slog.tech/about/qa.html)
4. [钱往 版本中心（各平台版本日期、自定义资产更新日志、Roadmap）](https://www.slog.tech/changelog)
5. [钱往 App Store 页面（功能描述、内购价格、评分）](https://apps.apple.com/cn/app/%E9%92%B1%E5%BE%80-%E8%AE%B0%E8%B4%A6-%E6%8A%95%E8%B5%84%E8%B4%A6%E6%9C%AC-%E9%A2%84%E7%AE%97%E5%AD%98%E9%92%B1/id6446384233)
6. [同花顺投资账本 官方 FAQ（基金分红自动生成流水、定投自动记录）](https://tzzb.10jqka.com.cn/faq.html)
7. [同花顺投资账本 关于我们（官网，内容偏旧）](https://tzzb.10jqka.com.cn/aboutUs.html)
8. [FoxData：同花顺投资账本（免费、无内购、3.6 万评分 4.8）](https://foxdata.com/ru/app-marketing-analytics/1100654428/as/TW/%E5%90%8C%E8%8A%B1%E9%A1%BA%E6%8A%95%E8%B5%84%E8%B4%A6%E6%9C%AC-%E8%82%A1%E7%A5%A8%E5%9F%BA%E9%87%91%E8%AE%B0%E8%B4%A6-%E6%94%B6%E7%9B%8A%E6%9F%A5%E7%9C%8B/)
9. [鲨鱼资产管家（应用宝，2026-01-03）](https://sj.qq.com/appdetail/com.shark.assetmanager)
10. [16 款安卓个人记账 APP 大横评（少数派，2025-04-21）](https://pwa.sspai.com/post/98549)
11. [投资记录，从「有知有行」账本到定制 Excel 表格（知乎，2022-01-07）](https://zhuanlan.zhihu.com/p/454272957)

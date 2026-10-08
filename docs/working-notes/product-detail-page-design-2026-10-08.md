# 产品详情页通篇设计（与自选产品详情统一）· 2026-10-08

> 承接 issue [#1909](https://github.com/imoyao/fundmate/issues/1909)（验收①「详情页通篇设计定稿」）。
> 上游：#1133 需求细化评论 §6（形态已定：**独立路由，不做弹窗 / 抽屉**）、
> `./watchlist-type-dimensions-design-2026-09-10.md` §7（**两级模型已定**：行点击 → 抽屉速览 → 抽屉内「查看详情 →」→ 详情页）。
> 状态：**初稿，待评审定稿**。定稿后按 §11 拆实现卡（验收②）。

---

## 0. 一句话结论

**一个详情页、两个入口、按品类分层的区块集。** 路由独立（`/product/:symbol`），
速览抽屉保留为第二级不删；品类差异用「区块 + 降级 `—`」表达，不为每个品类建一套页面；
一期只做**基金 / ETF**，股票 / 指数 / 可转债 / 投顾组合 / 基金经理按数据可得性分期。

---

## 1. 现状盘点（设计要解决的问题，全部经代码实证）

| # | 事实 | 证据 | 对设计的影响 |
|---|------|------|--------------|
| 1 | **全仓没有产品维度路由**：`router/modules/*.ts` 只有 `LedgerDetail` / `PortfolioDetail` 两条 `:id` 详情路由 | `src/router/modules/asset.ts:211,245`；grep `:symbol\|:code` 0 命中 | 需新建路由 + 页面骨架（含手工注册与 `defineOptions.name` 一致性） |
| 2 | 聚合页产品卡点击 → **抽屉**，非跳转；抽屉内**无**「查看详情」入口 | `src/components/Aggregation/AggregationPage.vue:147-172,344-349` | 入口①要新增（保持行/卡点击语义不变） |
| 3 | 自选行点击 → 速览抽屉，底部「查看详情」是 **disabled + 「详情页开发中」** | `src/views/asset/watchlist/components/WatchlistQuickViewDrawer.vue:236-240` | 入口②只需启用按钮 + 接线 |
| 4 | 两套抽屉**互不复用**（聚合侧偏持仓分摊、自选侧偏行情速览），且抽屉里已堆了不少深度信息 | 同上两文件 | 详情页落地后必须回答「哪些留在抽屉、哪些下沉详情页」，否则同一信息两处维护（§7） |
| 5 | 代码里已预留 **3 处 `#1909` 接线点**，现统一跳 `/watchlist` | `views/welcome/index.vue:176`、`components/WatchlistWidget/index.vue:234,289` | 入口③：详情页落地后恢复 `select` 事件 |
| 6 | **没有产品级身份 resolver**：前端无 `symbolIdentity` / 身份 key 帮助函数 | grep `symbolIdentity\|symbol_norm\|identityKey` 前端 0 命中 | 多入口 → 同一详情页，必须有**单一**身份归一逻辑（§3） |
| 7 | `GET /api/positions/` **不支持按 symbol 过滤**（只有 `group_by/page/per_page/ledger_id`） | `backend/app/domains/positions/views.py:36-39` | 「我的持仓」区块需新增过滤参数或改走聚合接口（§9-C3） |
| 8 | XIRR 只有 `scope=position / portfolio（+family）`，**无标的存在级** | `backend/app/domains/performance/views.py:33-39` | 产品级「持有年化」需后端补 scope（§9-C7） |
| 9 | 后端 `funds` 域仅 9 个端点，**无基金详情端点**（G5） | `backend/app/domains/funds/views.py`；`./fundfof-gap-analysis-2026-09-30.md:134` | 公开资料区块只能按需取现有端点，缺的进实现卡 |
| 10 | 价格序列只有 `getWatchlistTrends(symbols, days=60)`，且**语义上属自选域** | `src/api/watchlist.ts:179` | 走势区块要解决「非自选标的从哪拿序列」（§9-C4） |
| 11 | 品类判定硬约束：**symbol 前缀不能单独当判据**，须按 `asset_type` 两步法回查 | `docs/features/watchlist.md:228` | 路由不带品类，品类由后端解析（§3.3） |

---

## 2. 设计原则

1. **持仓视角优先，不做全市场研究页。** 本产品是记账软件，详情页回答的是
   「**我**与这只标的关系 + 这只标的公开资料」，不是 fundfof 那种 13-tab 全市场研究
   （业绩归因 / 持股分析 / 行业分析——其前置数据 `fund_holdings` 明细、行业配置、基准日线
   我方均缺，见 `./fundfof-gap-analysis-2026-09-30.md` G3/G4/G9）。同源于该文 §2.5 第 3 条
   「**持有人的视角**」，也是数据策略第一原则（产品场景驱动，非工程完整性驱动）。
2. **两级渐进（已定，不改）**：抽屉 = 速览 + 轻编辑；详情页 = 深度只读 + 操作跳转。
   详情入口**不占**行点击 / 卡片点击语义。
3. **一个详情页**：品类差异用「区块是否渲染 + 数据降级 `—`」表达，**禁止**为品类新建平行页面
   （反面先例：#1133 期间 `/funds` 与 `/asset/fund-aggregation` 同品类两套页面撞车）。
4. **数据按需取、可降级**：详情页打开只发「身份解析 + 首屏必需」请求，深度区块各自懒加载；
   L3 参考展示类（公司 / 经理 / 全称 / 费率）缺了显示 `—`，不影响可用性。
5. **一层页头 + 强制复用**：`PageHeaderBar #action` 承载返回与页面级操作，
   页头下不再起工具条（`frontend/design.md`「页头操作槽与『一层页头』原则」，#1714）；
   区块一律 `CardBlock + SectionHeader`，指标一律 `MetricCard / MetricGrid`。
6. **身份与展示契约不可违背**：前端**不得**自行拼 / 剥交易所前缀
   （`frontend/design.md` 资产代码展示契约 D35/D36）；组合类标的（投顾组合 / 基金经理）
   **不展示代码**，由「名称 + 品类 + 平台/主理人」承担识别
   （`docs/design/components.md`「组合类标的的识别信息呈现」）。
7. **编辑就近、详情只读**：备注 / 标签 / 总价分摊 / 记一笔等编辑动作留在其**数据所属页面**
   （抽屉、账户详情、组合详情），详情页只给入口跳转，不复制编辑表单。

---

## 3. 路由与身份解析

### 3.1 路径方案

| 方案 | 形态 | 评价 |
|---|---|---|
| **A（推荐）** | `/product/:symbol` + `?market=&venue=` | 主键用户可读、可分享；`market`/`venue` 仅用于消歧（`000001` 上证指数 vs 平安银行），多数场景为空串 → URL 干净 |
| B | `/product/:symbol/:market/:venue` | 全路径参数，空值时出现 `//`，路由守卫与面包屑都要特判 |
| C | `/product?symbol=&market=&venue=` | 纯 query，路径不可读，分享语义差 |
| D | 后端 `symbol_norm`（`EXCHANGE:SZ159915`） | 把存储形态暴露进 URL；watchlist 侧无此字段，且含类型信息——**否决**（身份字段归后端，URL 只做寻址） |

- 路由注册：新建 `src/router/modules/product.ts`，`name: "ProductDetail"`、
  `meta.requiresAuth`；组件 `src/views/product/detail.vue`，
  `defineOptions.name` 必须与路由 name 一致（否则 keep-alive 失效）。
- 手工注册，**不**依赖 `import.meta.glob` 自动成路由（#1703 实证）。

### 3.2 单一 resolver（新增，所有入口共用）

新建 `src/utils/productIdentity.ts`（或 `src/router/productKey.ts`）：

```ts
// 只读字段、不改写 symbol 字符串（D35/D36 契约）
export interface ProductRef { symbol: string; market?: string; venue?: string }
export function productRoute(r: ProductRef): string        // → /product/000001?market=SZ&venue=EXCHANGE
export function parseProductRef(route): ProductRef          // 反解
export function productKey(r: ProductRef): string           // `${symbol}|${market}|${venue}`，用于去重与匹配
```

- **入口侧适配**：自选行（`symbol+market+venue` 三字段现成）、持仓 / 聚合卡
  （`symbol` + `market` + `asset_type`，无 `venue` 时按 `venueOfAssetType()` 推导，
  单点复用 `src/constants/market.ts`，禁止字面量 `OTC`/`EXCHANGE` 散写）。
- 禁止各页面自己拼字符串跳转——这是 §1 #6 消灭的重复。

### 3.3 品类判定与数据解析（两步法）

**路由不带品类，品类由后端解析**（`docs/features/watchlist.md:228`：symbol 前缀不能单独当判据）。
新增轻量端点：

```
GET /api/products/resolve/?symbol=&market=&venue=
→ { asset_type, market, venue, display_name, in_watchlist, has_position, source }
```

- 落点：统一 service 收口跨域两步法（先自选 / 持仓判身份，再按 `asset_type` 回查
  market 域实体：`fund→funds`、`index→index_catalog`、`manager→managers`（剥 `MGR_`）、
  `portfolio→advisor_portfolios`、股票→证券名录），**禁止前端自行推断**。
- 前端拿到 `asset_type` 后再分派按需请求（§5 区块各自取数）。
- 解析失败（找不到任何实体）→ 404 态（§8 空态），不是白屏。

---

## 4. 进入点矩阵（一期全部打通）

| # | 入口 | 现状 | 目标行为 | 分期 |
|---|------|------|----------|------|
| 1 | 自选页行点击 → 速览抽屉 | 底部「查看详情」disabled + 「详情页开发中」 | 启用 → `productRoute(item)` 关抽屉跳详情 | 一期 |
| 2 | 聚合页 `/funds` `/stocks` 产品卡 → 抽屉 | 抽屉无详情入口 | 抽屉头部下沿加「查看详情 →」（与自选抽屉同款同位） | 一期 |
| 3 | 首页自选摘要（`WatchlistWidget` / welcome） | 统一 `router.push('/watchlist')`，`select` 事件被摘 | 恢复 `select`，点击行直达详情；`/watchlist` 保留为「更多」 | 一期 |
| 4 | 账户详情「持仓明细」行 | 行点击 → `PositionTransactionsDrawer`（交易流水） | **不动行点击**；抽屉头部加「查看详情 →」 | 一期 |
| 5 | 组合详情「持仓明细」行 | 同上无入口 | 同 #4 | 二期 |
| 6 | 全局搜索 | 仅服务「添加自选」两处（`ExploreAddSection` / `AddToWatchlistModal`），非导航 | 详情页落地后可挂导航（**不进一期**，避免扩范围） | 远期 |
| 7 | 直接访问 / 分享 URL | 不存在 | 完整可用（含 404 态、登录门禁） | 一期 |

> 入口设计的一致规则：**抽屉是速览，抽屉内才有「查看详情 →」**；列表行 / 卡片点击永远
> 不直接跳详情（守卫两级模型不被破坏）。

---

## 5. 信息架构（页面骨架）

```
PageHeaderBar  标题=产品名  副标题=# 代码 · 品类 · 数据日期
├─ #action：[返回] [＋加入自选/已在自选] [记一笔]
│
├─ Hero 行（CardBlock）
│   资产类型徽章 AssetTypeBadge + 名称 + 代码（组合类不展示代码）
│   最新价/净值 MoneyDisplay + 涨跌 RiseFallText（或 PnlDualLine + RealtimeEstimateToggle）
│   状态 chips：已持仓（N 个账户）· 已自选 · 分组/标签（只读）
│
├─ A 我的持仓（CardBlock，登录且 has_position 时渲染）        [数据：user 域]
│   合计：市值 / 份额 / 成本 / 持仓收益 / 持有年化(XIRR)
│   分渠道表：账户 · 份额 · 成本价 · 市值 · 收益（ProductDisplay + MoneyWithRatio）
│   操作：交易流水（跳 PositionTransactionsDrawer 场景）· 总价分摊（跳聚合抽屉场景）
│
├─ B 走势（CardBlock）                                        [数据：market 域]
│   区间 SegmentedControl：1M / 3M / 6M / 1Y（>60 日依赖 #1535 落库）
│   曲线：净值 / 收盘价（复用共享图表组件，禁自绘）
│   口径脚注：数据日期 · 来源
│
├─ C 公开资料（CardBlock）                                     [数据：market 域，L3 按需]
│   基金：管理人 / 公司 / 类型 / 成立日 / 业绩基准（有则显）/ 费率表（申购·赎回）
│   缺失项显示 `—`，不占位加载
│
├─ D 品类差异化区块（Block per asset_type，见 §6）            [分期]
│
├─ E 关联标的（CardBlock，二期）
│   跨渠道关联（ETF↔场外联接 / 指数↔场内ETF，#1394）· 组合成分 · 指数→ETF
│
└─ 页脚：数据日期 · 免责声明（固定文案口径，与 AppFooter 一致）
```

**取数编排**（防全量拉取）：

1. `resolve` → 拿 `asset_type` / `in_watchlist` / `has_position`；
2. 首屏必需：Hero 行情（自选 item 或现有净值/行情端点）+ A 区块（若 `has_position`）；
3. B / C / D 各自 `onMounted` 懒加载，失败仅降级本区块，不整页报错；
4. 区块级 `PageSkeleton` 遵守 200ms 阈值（`docs/design/components.md` PageSkeleton 铁律 4）。

---

## 6. 品类差异化矩阵（分期依据 = 数据可得性）

| 品类 `asset_type` | 一期可得数据 | 缺口 | 分期 |
|---|---|---|---|
| **基金（场内 ETF / 场外）** | 持仓（聚合接口）、净值（`fetchFundNav`/`useNavCache`）、费率（`getFundFeeRates`）、经理/公司名、60 日走势 | 产品级 XIRR（C7）、长历史走势（#1535）、基金详情端点（G5）、最大回撤口径（#1410） | **一期** |
| 股票 | 持仓、价格区间（`getSecurityPriceRange`）、行业字段 ⚠️填充率待核 | 长历史、基本面 | 二期 |
| 指数 | 估值（PE/分位，落库依赖 #1407）、`index_daily`（仅 10 个 `.WI` 有日线） | 估值长历史、宽基日线（`index-daily` 补强进行中） | 二期 |
| 可转债 | 静态条款（转股价 / 溢价率 / 强赎价，#1393/#1400） | YTM / 接近加速度（数据源待定） | 二期 |
| 投顾组合 | 自选侧已有：配置目标 / 组合净值 / 策略简介 / 成分基金 / 调仓（`getAdvisorHoldings` / `getAdvisorAdjusts`）、区间收益（#1392） | 跨平台一致性、业绩基准 | 三期 |
| 基金经理 | 任职基金列表、公司 | `managers` 字段空（G6：`appointment_date`=0、`end_date` 100% NULL）→ 做不了任期/风格 | 三期（依赖 G6 补抓） |

> **降级规则**：任一品类区块的数据拿不到 → 该区块整体不渲染或显示 `—`，
> **禁止**用 mock / 演示数据占位（G1 演示债教训）。

---

## 7. 与抽屉 / 既有页的职责边界（防双份维护）

| 能力 | 归属 | 理由 |
|---|---|---|
| 名称 / 代码 / 品类 / 最新价 / 涨跌 | 抽屉 + 详情页**共用组件** | 速览与详情首屏本就该同源，禁止各写一份 |
| 持有份额 / 成本 / 市值 / 收益 | 抽屉（速览 4 格）+ 详情页 A 区块（分渠道明细） | 抽屉给结论，详情页给明细——**数据同源不同粒度** |
| 备注 / 标签 / 分组编辑 | 抽屉（既有） | 编辑就近，详情页只读展示并回链 |
| 总价分摊 | 聚合抽屉（既有 `allocateValue`） | 同上；详情页 A 区块给「去分摊 →」跳转 |
| 交易流水 | `PositionTransactionsDrawer`（既有） | 同上 |
| 走势曲线 / 费率 / 关联标的 | **仅详情页** | 信息量大，属「详情页才该有」的第二级 |
| 投顾成分与调仓 | 抽屉（既有）+ 详情页 D（复用同一组件） | 已实现，避免重写 |

**结论**：抽屉**不删、不瘦身到空壳**，但抽屉内不再新增深度区块；
新增深度信息一律进详情页。评审时需确认此边界（§12 待拍板 ③）。

---

## 8. 视觉基线（与自选详情统一，写给实现者）

- **页头**：`PageHeaderBar`，返回按钮与操作进 `#action`；页头下不加工具条（#1714）。
- **区块**：一律 `CardBlock` + `SectionHeader`（含 `info` 口径说明）；间距由容器 `gap: var(--space-section)` 控制。
- **指标**：`MetricCard` / `MetricGrid`（`--metric-basis` 响应式三档，勿手写宽度）。
- **数值**：金额 `MoneyDisplay`、涨跌 `RiseFallText` / `MoneyWithRatio`、
  涨红跌绿只用语义变量 `--color-rise` / `--color-fall`，**禁止硬编码 hex**；
  数字一律 `font-variant-numeric: tabular-nums` + 等宽字体。
- **多选一切换**（区间 / 维度 / 视图）：一律 `SegmentedControl`（唯一实现，守卫 `scripts/guard_segmented.py`）。
- **代码展示**：渲染后端返回的 `symbol` 原样，不拼不剥；组合 / 经理类**不展示代码**。
- **加载 / 空态**：`PageSkeleton`（200ms 阈值）+ 空态走品牌隐喻与定调文案
  （`frontend/design.md`「空状态 / 加载态品牌隐喻」），404 态给出「回到自选」出路。
- **暗色**：只用令牌，`design.dark.md` 自动继承，不写暗色特例。
- **免责**：页脚固定文案「市场有风险，投资需谨慎。本平台内容仅供参考，不构成任何投资建议。」

---

## 9. 数据可得性与缺口 → 实现卡映射

| # | 能力 | 现状 | 缺口 / 动作 | 归属卡 |
|---|---|---|---|---|
| C0 | 身份解析端点 `GET /api/products/resolve/` | 无 | 新增（收口两步法，跨域两步读集中到 service） | 卡1 |
| C1 | 路由 + 页面骨架 + resolver + 404 态 | 无 | 新增 `router/modules/product.ts`、`views/product/detail.vue` | 卡1 |
| C2 | 四个入口接线（自选抽屉 / 聚合抽屉 / 首页 Widget / 账户持仓抽屉） | disabled / 缺失 / 摘除 | 启用 + 恢复 `select` | 卡2 |
| C3 | 「我的持仓」区块 | `GET /api/positions/` **无 symbol 过滤** | 加 `symbol`（+`market`）过滤参数，或复用 fund/securities 聚合接口按 key 取组 | 卡3（含后端） |
| C4 | 走势区块 | `getWatchlistTrends` 仅自选语义、60 日 | 非自选标的取数路径 + 区间扩展（>60 日依赖 #1535） | 卡4 |
| C5 | 公开资料（费率 / 经理 / 公司） | 端点已有（`getFundFeeRates` 等） | 基金详情端点缺失（G5）→ 一期只用现有端点拼装 | 卡5 |
| C6 | 产品级持有年化 XIRR | 只有 `scope=position / portfolio` | 后端补 `scope=symbol`（跨账户按 symbol 汇总现金流） | 卡6 |
| C7 | 品类差异化区块（股票 / 指数 / 可转债 / 组合 / 经理） | 字段部分已有（`WatchlistItem` 已预留） | 按 §6 分期，逐批接 | 卡7（可再拆） |
| C8 | 高级洞察 Pro 面板（归因 / 风险 / 配置 + 付费墙） | **已有卡 #994** | 挂靠，不重复建卡 | #994 |

---

## 10. 不做什么（边界清单）

- ❌ 不做弹窗 / 抽屉形态的「详情页」（#1133 §6 已定独立路由）。
- ❌ 不做全市场研究视角的 13-tab（业绩归因 / 持股 / 行业 / 超额 / 相关性）——数据前置缺失，属远期且依赖 #861/#866 等。
- ❌ 不在详情页内复制编辑表单（备注 / 标签 / 分摊 / 记一笔均回链既有场景）。
- ❌ 不为单品类另建平行详情页；不新建与既有组件同类的自绘结构。
- ❌ 不用 mock / 演示数据占位（G1 教训）。
- ❌ 不在本卡（#1909）内实现任何功能代码——本卡只交付设计 + 拆卡。

---

## 11. 拆卡建议（验收②，定稿后创建）

| 卡 | 标题（草案） | 范围 | 依赖 | 里程碑 | 象阵 |
|---|---|---|---|---|---|
| 卡1 | feat(detail): 产品详情页路由与骨架 + 身份解析端点 | `resolve` 端点、路由注册、Hero + 空态/404、`productIdentity` helper、设计令牌合规 | — | M6 → 视情调 M2 | Q2 |
| 卡2 | feat(detail): 四入口接线到产品详情页 | 自选抽屉启用按钮、聚合抽屉加入口、首页 Widget 恢复 `select`、账户持仓抽屉入口 | 卡1 | M6 | Q2 |
| 卡3 | feat(detail): 「我的持仓」区块（含后端 symbol 过滤） | 后端 `positions` 过滤参数 + 前端分渠道表 + XIRR 占位 | 卡1 | M6 | Q2 |
| 卡4 | feat(detail): 走势区块（区间切换 + 非自选标的取数） | 取数路径、`SegmentedControl` 区间、>60 日依赖 #1535 | 卡1 | M6 | Q2 |
| 卡5 | feat(detail): 公开资料区块（费率 / 管理人 / 公司） | 现有端点拼装 + 降级 `—` | 卡1 | M6 | Q3 |
| 卡6 | feat(performance): XIRR 支持 `scope=symbol`（产品级持有年化） | 后端 scope + 测试 + 前端接线 | 卡3 | M6 | Q3 |
| 卡7 | feat(detail): 品类差异化区块 P1（股票 / 指数 / 可转债） | 按 §6 逐批，含数据缺口依赖（#1407/#1400/#1393） | 卡1 | M6 | Q3 |
| 卡8 | feat(detail): 品类差异化区块 P2（投顾组合 / 基金经理） | 依赖 #1392、G6 字段补抓 | 卡1、#1392 | M6 | Q4 |

> 卡1 是所有后续卡的前置；卡2 可与卡3 并行。所有卡创建后须挂里程碑 + `象阵`
> （全局硬规则），并在 #1909 评论区登记映射。

---

## 12. 待拍板（评审时逐条给结论）

| # | 问题 | 我的建议 | 影响 |
|---|---|---|---|
| ① | 路由形态 A/B/C/D | **A**（`/product/:symbol` + query 消歧） | 卡1 |
| ② | 一期品类范围 | **只做基金 / ETF**（数据最全），其余按 §6 分期 | 卡7/卡8 排期 |
| ③ | 抽屉是否瘦身 | **不瘦身、停止生长**（§7 边界） | 卡2 范围 |
| ④ | 是否需要线框图（项目惯例「实施前出图确认」） | 需要——卡1 开工前补一张 ASCII/HTML 线框 | 卡1 验收 |
| ⑤ | 走势区间默认档 | 默认 `3M`；无长历史时自动收敛到可用档 | 卡4 |
| ⑥ | 详情页是否接实时估值轮询 | 一期接（复用 `useRealtimeQuotes`，与自选同链路），开关用 `RealtimeEstimateToggle` | 卡1/卡4 |

---

## 13. 变更记录

- 2026-10-08 初稿（OpenCode）：完成现状实证（§1 十条）、路由与 resolver 方案、七入口矩阵、
  信息架构、品类分期矩阵、抽屉职责边界、C0–C8 拆卡草案与六项待拍板。待评审定稿。

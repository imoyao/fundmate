# 产品详情页通篇设计（与自选产品详情统一）· 2026-10-08

> 承接 issue [#1909](https://github.com/imoyao/fundmate/issues/1909)（验收①「详情页通篇设计定稿」、验收②「实现范围拆出并立执行卡」）。
> 上游：#1133 需求细化评论 §6（形态已定：**独立路由，不做弹窗 / 抽屉**）、
> `./watchlist-type-dimensions-design-2026-09-10.md` §7（**两级模型已定**：行点击 → 抽屉速览 → 抽屉内「查看详情 →」→ 详情页）。
> 状态：**v2（2026-10-08 用户评审后修订）**。v1 → v2 变更见 §13。

---

## 0. 一句话结论

**一套详情页体系：按品类分 URL、两个入口、Epic 汇总卡带分项子卡。**

- **路由按品类分段（v2 修订）**：路径段 = `asset_type`，`/fund/004369`、`/stock/SZ000001`、`/manager/MGR_xxx`，
  不用 `/product/:symbol` 这种「什么都往里塞」的形态；
- **一期品类：基金 / 股票 / 基金经理**；可转债一期**不做内部详情、只做集思录外链**；指数·ETF 二期、投顾组合三期；
- 速览抽屉保留为第二级不删（本期不瘦身，详情页上线后**复评**）；
- 品类差异用「区块 + 降级 `—`」表达，不为每个品类另建平行页面；
- **数据过渡期允许接雪球 / 天天基金 / fundfof 等第三方接口**，不强求全部后端自供（轻量化演进，合规边界见 §9.1）；
- 执行组织成 **Epic 汇总卡 + 分项子卡**（§11），总卡勾选即可看到实现了哪些、还差哪些。

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

### 3.1 路径形态（2026-10-08 拍板：**按品类分 URL**，废止 v1 的 `/product/:symbol`）

**路径段 = `asset_type`，一对一映射，不推断、不别名。** 映射表只有**一份**，
放在 `assetTypeToPath()` / `pathToAssetType()`（与 `productIdentity` 同文件）：

| `asset_type` | 路径形态 | 例 | 分期 |
|---|---|---|---|
| `fund` | `/fund/:symbol` | `/fund/004369` | 一期 |
| `stock` | `/stock/:symbol` | `/stock/SZ000001` | 一期 |
| `manager` | `/manager/:symbol` | `/manager/MGR_xxxx` | 一期 |
| `bond`（可转债） | `/bond/:symbol` | — | **一期只做集思录外链，不建内部详情**（§6） |
| `etf` | `/etf/:symbol` | `/etf/SZ159915` | 二期 |
| `index` | `/index/:symbol` | `/index/SH000300` | 二期 |
| `portfolio`（投顾组合） | `/portfolio/:symbol` | `/portfolio/ZHxxxx` | 三期，⚠️ 见下 |

- 消歧仍走 query：`?market=&venue=`（同品类跨市场同码，如 `000001`）。
- **路由注册**：新建 `src/router/modules/product.ts`，一条**带品类参数**的路由
  （`/product/:assetType/:symbol`，`path` 允许段白名单 = `ASSET_TYPE_VALUES` 的详情页子集），
  `name: "ProductDetail"`、`meta.requiresAuth`；组件 `src/views/product/detail.vue`，
  `defineOptions.name` 必须与路由 name 一致（否则 keep-alive 失效）。
  路由 path 写成**单一路由 + 品类段**而不是 7 条重复路由，是为了让 §3.2 的映射表仍只有一份；
  对外呈现的 URL 依然是 `/fund/004369` 这种分品类形态（`path: "/:assetType/:symbol"`）。
  手工注册，**不**依赖 `import.meta.glob` 自动成路由（#1703 实证）。
- **v1 `/product/:symbol` 为什么废止**：六类标的信息结构差异极大，塞进同一路径段后
  「URL 看不出品类」，还必须先 resolve 才知道自己在看什么；分品类 URL 让分享、
  日志、埋点、收藏夹天然携带品类信息，且与 `asset_type` 权威枚举一一对应、无别名歧义。
- ⚠️ **命名坑（三期前必须拍板）**：`/portfolio/:symbol`（投顾组合，外部平台码）
  与既有 `/asset/portfolios/:id`（我方组合详情，`router/modules/asset.ts:245`）前缀相近、
  语义完全不同。建议届时改用 `/advisory/:symbol`；一期不涉及，不阻塞。

### 3.2 单一 resolver（新增，所有入口共用）

新建 `src/utils/productIdentity.ts`：

```ts
// 只读字段、不改写 symbol 字符串（D35/D36 契约）
export interface ProductRef { assetType: string; symbol: string; market?: string; venue?: string }
export function assetTypeToPath(t: string): string     // asset_type → 路径段（唯一映射表）
export function productRoute(r: ProductRef): string    // → /fund/004369?market=&venue=
export function parseProductRef(route): ProductRef
export function productKey(r: ProductRef): string      // `${assetType}|${symbol}|${market}|${venue}`
```

- **入口侧适配**：自选行（`asset_type/symbol/market/venue` 四字段现成）、持仓 / 聚合卡
  （`symbol` + `market` + `asset_type`，无 `venue` 时按 `venueOfAssetType()` 推导，
  单点复用 `src/constants/market.ts`，禁止字面量 `OTC`/`EXCHANGE` 散写）。
- 禁止各页面自己拼字符串跳转——这是 §1 #6 消灭的重复。

### 3.3 品类判定与数据解析（两步法）

**路径里的 `asset_type` 只是「入口提示」，不是权威**——用户可以手输、收藏夹可能过期。
权威判定仍走后端两步法（`docs/features/watchlist.md:228`：symbol 前缀不能单独当判据）：

```
GET /api/products/resolve/?symbol=&market=&venue=&asset_type=
→ { asset_type, market, venue, display_name, in_watchlist, has_position, source }
```

- 前端把 path 上的 `asset_type` 传进去**供后端核对**：一致则直接用；不一致（404 或重定向到正确路径段）
  以**后端返回为准**，不信任手输路径。
- 落点：统一 service 收口跨域两步法（先自选 / 持仓判身份，再按 `asset_type` 回查
  market 域实体：`fund→funds`、`index→index_catalog`、`manager→managers`（剥 `MGR_`）、
  `portfolio→advisor_portfolios`、股票→证券名录），**禁止前端自行推断**。
- 前端拿到确认的 `asset_type` 后再分派按需请求（§5 区块各自取数）。
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

## 6. 品类差异化矩阵（分期依据 = 用户拍板的一期范围 + 数据可得性）

> **2026-10-08 拍板**：一期 = **基金 / 股票 / 基金经理**；**可转债一期不做内部详情，
> 改为「去集思录」外链**（条款类深度数据源未定，见 #1400）；指数 · ETF 二期、投顾组合三期。

| 品类 `asset_type` | 已可得数据 | 缺口 | 分期 |
|---|---|---|---|
| **基金 `fund`** | 持仓（聚合接口）、净值（`fetchFundNav` / `useNavCache`）、费率（`getFundFeeRates`）、经理 / 公司名、60 日走势 | 产品级 XIRR（B1）、长历史走势（#1535）、基金详情端点（G5）、最大回撤口径（#1410） | **一期** |
| **股票 `stock`** | 持仓、价格区间（`getSecurityPriceRange`）、行业字段 ⚠️填充率待核 | 长历史、基本面；行情可走第三方过渡（§9.1） | **一期** |
| **基金经理 `manager`** | `managers` 4,264 / `fund_managers` 34,809 **已落盘** → 任职基金列表可展示 | `appointment_date`=0、`start/end_date` 空 → **任期 / 风格 / 任职回报降级 `—`**（G6，修复方向是补字段抓取） | **一期（诚实降级）** |
| **可转债 `bond`** | — | 条款类数据源未定（#1400 需 cookie） | **一期：只做「去集思录」外链卡**，不建内部区块 |
| ETF `etf` | 走势、行情、跨渠道关联（#1394） | 与基金区块高度同构，可复用基金组件 | 二期 |
| 指数 `index` | 估值（PE / 分位，落库依赖 #1407）、`index_daily`（仅 10 个 `.WI` 有日线） | 估值长历史、宽基日线（`index-daily` 补强进行中） | 二期 |
| 投顾组合 `portfolio` | 自选侧已有：配置目标 / 组合净值 / 策略简介 / 成分基金 / 调仓（`getAdvisorHoldings` / `getAdvisorAdjusts`）、区间收益（#1392） | 跨平台一致性、业绩基准；路由命名坑（§3.1） | 三期 |

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

**结论（2026-10-08 拍板）**：抽屉本期**不瘦身**——保留现有信息量，但**停止生长**：
抽屉内不再新增深度区块，新增深度信息一律进详情页。
**详情页上线后复评是否瘦身**（届时抽屉已有详情页兜底，才具备瘦身条件；对应拆卡 B6）。

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

### 9.1 过渡期数据源策略（2026-10-08 拍板：轻量化演进）

**过渡期不强求所有数据由我方后端提供**——缺数据时可直接接第三方：

| 场景 | 可接的源 | 边界（红线） |
|---|---|---|
| 行情 / 走势 | 雪球、天天基金、腾讯行情（现有 `useRealtimeQuotes` 已用） | 只做**只读公开数据**；遵守 `external-source-policy-2026-09-30.md`（内部文档写明来源与风险、对外文案不提、**不绕鉴权**、可一键关停 + 静默降级） |
| 基金资料 / 费率 / 净值 | 天天基金、`useNavCache` 分级链路（#1133 决策） | 复用既有 `NavService`，不另起链路 |
| 深度分析类 | fundfof（若确有必要） | **对外发布前必须换源**；不绕鉴权；`fundfof_crowding.py` 的关停 + TTL 缓存 + 失败降级是模板 |

- **原则**：第三方源是**过渡加速器**，不是新债——每个接了第三方的区块都要能
  「关掉源 → 区块降级 `—` / 外链」，不得让页面不可用。
- **卡片承接**：接哪些源、接在哪一区块，在 A5 / A6 / B2 各卡内具体拍板，本卡只定边界。

### 9.2 缺口 → 卡片映射

| 能力 | 现状 | 缺口 / 动作 | 归属卡 |
|---|---|---|---|
| 身份解析端点 `GET /api/products/resolve/` | 无 | 新增（收口两步法，跨域两步读集中到 service） | A1 |
| 路由 + 页面骨架 + resolver + 404 态 | 无 | 新增 `router/modules/product.ts`、`views/product/detail.vue` | A2 |
| 四入口接线（自选抽屉 / 聚合抽屉 / 首页 Widget / 账户持仓抽屉） | disabled / 缺失 / 摘除 | 启用 + 恢复 `select` | A3 |
| 「我的持仓」区块 | `GET /api/positions/` **无 symbol 过滤** | 加 `symbol`（+`market`）过滤参数，或复用 fund/securities 聚合接口按 key 取组 | A4 |
| 走势区块 | `getWatchlistTrends` 仅自选语义、60 日 | 非自选标的取数路径 + 区间扩展（>60 日依赖 #1535）+ 第三方过渡源（§9.1） | A5 |
| 基金资料 / 费率 | 端点已有（`getFundFeeRates` 等，`funds` 域共 9 个） | 基金详情端点缺失（G5）→ 一期先拼装，**拼不出首屏就在 A6 内直接补端点**（禁止悬空） | A6 |
| 股票 / 基金经理 / 可转债区块 | 字段部分已有（`WatchlistItem` 已预留；`managers` 已落盘但字段空） | 按 §6 分期；可转债走外链 | A7 / A8 / A9 |
| 产品级持有年化 XIRR | 只有 `scope=position / portfolio` | 后端补 `scope=symbol`（跨账户按 symbol 汇总现金流） | B1 |
| fundfof 实现方式 / 第三方源边界 | 已有 3 份研究文档（tab 白名单 / 缺口 / 真库实证），**缺「怎么实现的」** | 补调研（数据源、图表编排、接口调用链） | B2 |
| ETF · 指数 / 投顾组合 / 关联标的区块 | 部分已有 | 按 §6 二、三期 | B3 / B4 / B5 |
| 速览抽屉是否瘦身 | 本期不瘦身（§7） | 详情页上线后复评 | B6 |
| 高级洞察 Pro 面板（归因 / 风险 / 配置 + 付费墙） | **已有卡 #994** | 挂靠，不重复建卡 | #994 |

---

## 10. 不做什么（边界清单）

- ❌ 不做弹窗 / 抽屉形态的「详情页」（#1133 §6 已定独立路由）。
- ❌ 不做全市场研究视角的 13-tab（业绩归因 / 持股 / 行业 / 超额 / 相关性）——数据前置缺失，属远期且依赖 #861/#866 等；**这是 B2 调研要回答的「它怎么做、我们哪些照抄、哪些不做」**。
- ❌ 不在详情页内复制编辑表单（备注 / 标签 / 分摊 / 记一笔均回链既有场景）。
- ❌ 不为单品类另建平行详情页；不新建与既有组件同类的自绘结构。
- ❌ 不用 mock / 演示数据占位（G1 教训）。
- ❌ 不在本卡（#1909）内实现任何功能代码——本卡只交付设计 + 拆卡。
- ❌ **一期不做可转债内部详情**（改集思录外链）、**不做线框图**（实现卡开工时按需补）。

---

## 11. 拆卡方案（验收②：Epic 汇总卡 + 分项子卡）

> 组织方式（2026-10-08 拍板）：**一张汇总卡（Epic）带子卡清单**，子卡独立原子、
> 各自挂里程碑与象阵；总卡勾选即看「实现了哪些、还差哪些」。
> **卡号在创建后回填到 §11.3 与 #1909 评论区。**

### 11.1 一期（P0，基金 / 股票 / 基金经理）

| 卡号 | 标题（草案） | 范围 | 依赖 | 象阵 |
|---|---|---|---|---|
| A1 | `feat(detail): 产品身份解析端点 GET /api/products/resolve/` | 后端两步法收口 + `in_watchlist` / `has_position` + path 品类核对 | — | Q2 |
| A2 | `feat(detail): 详情页路由与骨架` | 路径段=`asset_type` 单点映射、`productIdentity` helper、Hero、404/空态、令牌合规 | A1 | Q2 |
| A3 | `feat(detail): 四入口接线` | 自选抽屉启用、聚合抽屉加入口、账户持仓抽屉入口、首页 Widget 恢复 `select` | A2 | Q2 |
| A4 | `feat(positions): positions 按 symbol 过滤 + 「我的持仓」区块` | 后端过滤参数 + 前端分渠道表 + 合计（XIRR 占位等 B1） | A2 | Q2 |
| A5 | `feat(detail): 走势区块` | 区间切换 + 非自选标的取数 + 第三方过渡源（§9.1）+ 降级 | A2 | Q2 |
| A6 | `feat(detail): 基金详情区块` | 资料 / 费率 / 管理人 + 降级；**拼不出首屏就在此卡内补 funds 详情端点（G5）** | A2 | Q2 |
| A7 | `feat(detail): 股票详情区块` | 行情 + 持仓 + 基本资料，缺数据降级 | A2 | Q2 |
| A8 | `feat(detail): 基金经理详情区块` | 任职基金列表；任期 / 风格字段空 → 诚实降级 `—` | A2 | Q2 |
| A9 | `feat(detail): 可转债详情改集思录外链卡` | 一期不做内部详情，只做外链 + 说明 | A2 | Q2 |

### 11.2 二期 / 深化（P1）

| 卡号 | 标题（草案） | 范围 | 依赖 | 象阵 |
|---|---|---|---|---|
| B1 | `feat(performance): XIRR 支持 scope=symbol` | 产品级持有年化（跨账户汇总现金流）+ 测试 + 前端接线 | A4 | Q4 |
| B2 | `调研: fundfof 详情页实现方式补充 + 第三方数据源接入边界` | 数据源 / 图表编排 / 接口调用链；产出「照抄 / 不做」清单 | — | Q4 |
| B3 | `feat(detail): ETF 与指数详情区块` | 二期货品；依赖 #1407（指数估值长历史） | A2 | Q4 |
| B4 | `feat(detail): 投顾组合详情区块` | 三期货品；**开工前拍板路由命名**（`/portfolio` vs `/advisory`）；依赖 #1392 | A2、#1392 | Q4 |
| B5 | `feat(detail): 关联标的区块` | ETF↔场外联接 / 指数↔场内 ETF | A2、#1394 | Q4 |
| B6 | `复评: 速览抽屉是否瘦身` | 详情页全量上线后复评（§7） | A3 | Q4 |

### 11.3 卡号回填（创建后填）

| 卡号 | issue |
|---|---|
| Epic | 待回填 |
| A1–A9 / B1–B6 | 待回填 |

> 依赖关系：**A1 → A2 是唯一硬前置**，A3–A9 可并行；B 系列等一期落地后排期。
> 所有卡创建时挂里程碑 M6（与 #1909 同）+ 象阵标签，排期时可整体上移到 M2。

---

## 12. 拍板记录（2026-10-08 用户评审）

| # | 问题 | 结论 |
|---|---|---|
| ① | 路径形态 | **按品类分 URL，路径段 = `asset_type`**（`/fund/` `/stock/` `/manager/` …）；v1 `/product/:symbol` 废止（§3.1） |
| ② | 一期品类 | **基金 / 股票 / 基金经理**；可转债 → 集思录外链；指数·ETF 二期、投顾组合三期（§6） |
| ③ | 抽屉是否瘦身 | 本期**不瘦身**、停止生长；**详情页上线后复评**（B6） |
| ④ | 线框图 | **一期不做**（实现卡开工时按需补） |
| ⑤ | 走势区间默认档 | 默认 `3M`，无长历史自动收敛到可用档（A5 内落实） |
| ⑥ | 详情页是否接实时估值 | 一期接（复用 `useRealtimeQuotes`），开关用 `RealtimeEstimateToggle`（A2/A5 内落实） |
| ⑦ | 数据来源 | **过渡期可接雪球 / 天天基金 / fundfof**，不强求后端自供；边界见 §9.1 |
| ⑧ | 执行组织 | **Epic 汇总卡 + 分项子卡**，勾选看进度（§11）；`issue 结构` 而非「页面总分结构」 |

---

## 13. 变更记录

- **2026-10-08 v2（用户评审后修订）**：① 路由由 `/product/:symbol` 改为**按品类分段**
  （路径段 = `asset_type`，含 `/portfolio` 与 `/asset/portfolios` 的重名坑登记）；
  ② 一期品类改为**基金 / 股票 / 基金经理**，可转债改集思录外链、指数·ETF 转二期、投顾组合转三期；
  ③ 新增 §9.1 **过渡期第三方数据源策略**（雪球 / 天天基金 / fundfof + 三条红线）；
  ④ 抽屉瘦身由「不瘦身」改为「不瘦身 + **详情页上线后复评**」（B6）；
  ⑤ 线框图移出一期；⑥ 拆卡改为 **Epic + A/B 两批共 15 张子卡**；
  ⑦ 新增 §12 拍板记录（八项）。
- 2026-10-08 初稿（OpenCode）：完成现状实证（§1 十条）、路由与 resolver 方案、七入口矩阵、
  信息架构、品类分期矩阵、抽屉职责边界、C0–C8 拆卡草案与六项待拍板。评审后作废的 v1 拍板建议
  已被本表取代。

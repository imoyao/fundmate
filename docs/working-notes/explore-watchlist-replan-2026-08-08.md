# 探市 × 自选 重新评估纪要（2026-08-08）

> 性质：内部备忘（`docs/working-notes/` 全目录屏蔽出构建，不对外）
> 触发：U1 总纲《fundmate 总体方案与落地总纲》（下载目录版，2026-07-22/23 更新）信息过期——① fundmate 功能已更新（P1-22 登录认证、P1-23 多用户、温度模块 B1–B4、#807 实时行情组件实际已落地）；② 基估宝官方已更新至 v2.4.1（2026-08-02 最后提交）。
> 本文目的：刷新事实基线 → 重新评估「参考基估宝实现什么」→ 探市/自选区分与迁移方案 → 记录发现的问题。所有结论带 file:line 证据。

---

## 1. 事实基线刷新

### 1.1 基估宝（real-time-fund）v2.4.1 功能全貌（2026-08-08 实证）

> 证据：仓库 file tree（`app/components/` 60+ 组件、`app/hooks/` 12 个、`app/stores/` 4 个）、README（1.6k star）、`doc/localStorage 数据结构.md`、提交历史（最近 2026-08-02 更新群二维码；2.4.1 修复东证指数显示）。
> **与 U1 总纲（7-22 调研）相比的增量**：总纲当时只覆盖「实时估值 + 自选 + OCR 截图导入 + Pro 限额」，v2.4.1 已扩展出完整「迷你记账 + 云同步 + 收益日历」体系。

| 能力域 | 基估宝 v2.4.1 实现 | 组件/机制（证据） |
|---|---|---|
| 实时估值 | 多数据源可选：官方(fundgz) / 搜狐基经(sina_ds2/ds3) / 天天基经；每基金标 `valuationSource` + `DataSourceAccuracyBadge` 准确度徽章 | `FundDataSourceSelector`、`DataSourceAccuracyBadge`、localStorage 文档 `valuationSource/dataSource` |
| 估值分时图 | 盘中估值分时序列缓存 `fundValuationTimeseries`（`{code: [{time,value,date}]}`，不云同步） | `FundValuationTrendChart`、`lib/valuationTimeseries.js` |
| 历史净值/趋势 | 历史净值弹窗 + 净值趋势图 + 每日收益 | `FundHistoryNetValue(Modal)`、`FundTrendChart`、`FundDailyEarnings` |
| 重仓追踪 | 前 10 大重仓股 + 盘中行情追踪，可展开收起（折叠状态记忆） | `FundCard`、`collapsedCodes/collapsedTrends` |
| 自选 | favorites + 系统「自选」分组（预置 id='fav'） | localStorage `favorites/groups` |
| 分组 | 自定义分组 + 移动弹窗 + 分组持仓 + 分组收益汇总 | `GroupManageModal`、`MoveGroupModal`、`groupHoldings`、`GroupAccountSummaryCard` |
| 持仓/交易 | 持仓份额+成本（`holdings`/`groupHoldings`）、买入/卖出交易、**待净值交易 `pendingTrades`（3pm 后买入挂起，净值更新后自动入账）**、基金转换、分红方式 | `TradeModal`、`HoldingEditModal`、`HoldingActionModal`、`PendingTradesModal`、`FundConvertModal`、`DividendMethodModal` |
| 定投计划 | 按日/周/月自动生成买入，**全局/分组两级 scope**（`dcaPlans: {__global__: {...}}`），自动迁移旧扁平结构 | `DcaModal`、`useTradingDay` |
| 每日收益日历 | 每日收益历史记录（按天+按基金），组合日收益聚合，收益日历视图 | `MyEarningsCalendarPage`、`lib/dailyEarnings.js` |
| 云端同步 | Supabase：**15 个 key 整包同步**，`localUpdatedAt` 版本戳 + 冲突时弹窗让用户选一方（LWW 交互版）；登录后自动上云 | `useSyncManager`、`lib/supabase.js`、`CloudConfigModal` |
| 数据管理 | JSON 导出/导入（**按 key 合并策略**：funds 按 code 去重、transactions 按 id 去重追加、customSettings 浅合并……）、PWA、屏幕常亮 | `SettingsModal`、`PwaRegister`、`KeepScreenAwake` |
| 排序/视图 | 自定义排序规则（估值涨跌/持仓收益/持有金额等，可组合启停）+ 默认模式拖拽排序；卡片/列表视图切换；折叠状态记忆 | `SortSettingModal`、`collapsedEarnings`、`viewMode` |
| OCR 截图导入 | 客户端 tesseract.js → Edge Function(AINX gpt) → 确认导入，每日限 5 次 | `ScanButton`、`useScanImport`、`doc/edgeFunction/analyze-fund.ts` |
| 行情/板块 | 大盘指数（可勾选显示）、关联板块（基金追踪目标 CSV + secid 映射）、全板块弹窗 | `MarketIndexAccordion`、`AllSectorsModal`、`MarketTab` |
| 其它 | 登录（邮箱 OTP + GitHub OAuth）、CLI 工具 `@jigubao/cli`、公告/更新日志/教程抽屉、捐赠弹窗、明暗主题 | `LoginModal`、`UserMenu`、`Announcement`、`UpdateLogModal`、`TutorialDrawer`、`DonateModal` |

**架构要点**（CLAUDE.md 确认）：localStorage（`storageStore`）是**主数据库**，Supabase 同步是**可选次要**；纯 JSX 无 TS；全部外部数据经 JSONP/script 注入（无 fetch）。

### 1.2 fundmate 现状刷新（对比 U1 总纲 §2.2）

| 项 | U1 总纲（7-22） | 现状（2026-08-08） |
|---|---|---|
| 登录认证 | 计划中 | ✅ P1-22 已完成：后端 Supabase JWT 验签 + 白名单鉴权（`core/auth.py`），探市/温度计/health 免登录，其余需登录（decisions D2/D4） |
| 多用户 | 无 | 🚧 P1-23 进行中：`family_id` 迁移 + 三档分权（D1/D3）；后端 `watchlist` 表已挂 `FamilyScopedMixin` |
| 自选实时行情 | #807 成功标准未达成（roadmap 曾记「三组件缺失」） | ✅ **已实现**：`useRealtimeQuotes` + `RealtimeWarningBanner` + `RealtimeStatusIndicator` 均存在并集成于 `views/asset/watchlist/index.vue`（:1002-1004 import、:244/247 使用）。roadmap P1-08 与 watchlist.md 的过期描述已由 2026-08-08 triage 更新拉平（成功标准 1–7 关闭、8–11 拆 #821） |
| 温度模块 | 硬编码 + 文案踩线 | ✅ B1/B2/B3/B4 已落地（`temperature-architecture-plan.md`）：阈值权威化、`jisilu_indicator` 带 level、短中长 `temperature_bands`、`insights/conclusion` 后端归集 |
| 乖离率 | — | ✅ P1-21 已放开（SKIP_BIAS=False，直连数据源） |
| 探市免登录策略 | — | `/explore` 靠路由白名单、`/temperature` 靠 `meta.requiresAuth=false`，**两套写法不一致** |
| 前端 Supabase | 已接 auth | 已接 auth，但**自选数据源未接 Supabase**：主站自选走后端 SQLite API，探市迁移却直连 Supabase 表（见 §2.1） |

---

## 2. 探市页 5 个问题的实证结论

### 2.1 问题 1：刷新后自选数据丢失 —— 属实且严重（双端丢失）

**根因链（全证据）**：

1. 探市观察列表**唯一数据源是 localStorage** `showbuy_explore_v1`：`useLocalHoldings.ts:4,39`（`readStorage()` 在模块加载时同步读一次）；`explore/index.vue:426-449` 用 `useLocalHoldings()` 渲染表格。
2. 登录后 500ms 自动触发迁移：`useSupabaseAuth.ts:76-81`（`SIGNED_IN` → `setTimeout 500ms` → `checkAndMigrateExploreData`）。
3. 迁移**成功后无条件删除本地 key**：`useSupabaseAuth.ts:106-107`（`removeItem("showbuy_explore_v1")` + 标记 `showbuy_explore_migrated`）。
4. 探市页**不回读云端**（无任何 Supabase 读取逻辑）→ 刷新后 `readStorage()` 返回 `[]` → **观察列表消失**。
5. 迁移目标写入 **Supabase `watchlist_items` 表**（`useSupabaseAuth.ts:135-143`），而主站自选页走**后端 API** `/api/watchlist/items/`（`frontend/src/api/watchlist.ts:128`），后端是 **SQLite `watchlist` 表**（`backend/app/domains/watchlist/models.py:16`）→ **两套完全割裂的数据源**，迁移后主站也看不到。
6. 附带缺陷：
   - **成本/份额不迁移**：只迁 `symbol/name/type/venue`（`useSupabaseAuth.ts:137-143`），`costPrice/quantity` 丢弃；
   - 登出不清 `showbuy_explore_migrated`（`SIGNED_OUT` 只清 user/session，:84-87），换账号登录不再重迁；
   - 迁移失败仅 `console.error`（:109-111），无重试无提示；
   - 迁移**无确认弹窗**（与 #808 设计「注册后弹窗询问（强阻断）」不符，被静默自动迁移替代）。

**结论**：U1 总纲 §5.4 说「迁移桥已写，直接复用」——**复用前提已失效**：该桥写错了数据源（Supabase 直连 vs 后端 API），且删除本地数据时机过早。此 bug 同时违反 #808 成功标准「注册后数据迁移成功率 100%」。

### 2.2 问题 2：探市与主站自选的关系 —— 需统一到后端 API

- 探市匿名：localStorage（`useLocalHoldings`）—— 设计如此（#808），保留。
- 迁移落点：应改为**主站自选后端 API**（`/api/watchlist/items/`，带 family_id），而非 Supabase 直连。主站自选页、探市迁移、未来多端同步应共用一个权威源（后端 SQLite → 未来 Postgres/Supabase，P2-23）。
- Supabase `watchlist_items` 表：前端直连残留（历史实现），与后端 `watchlist` 表命名/结构均不同，**应从迁移路径移除**（P2-23 云同步落地时再定云端表结构，避免先铺错表）。

### 2.3 问题 3：登录后跳转逻辑 —— 现状无注册 CTA，也无登录态分支

- 探市页**当前没有任何「立即注册/立即使用」按钮**：grep「立即/注册/开始体验/查看演示」仅命中「添加观察」按钮（`explore/index.vue:235`）；#808 设计文档的 HERO 区 CTA、底部转化区、损失厌恶文案**均未实现**。
- 用户感知的「登录后仍显示注册类按钮」大概率来自：导航栏「自选」按钮（`MarketHeader/config.ts:27`，primary 样式）未登录点击 → 路由守卫踢到 `/login`（`router/index.ts:247-269`），登录页含「立即注册」切换链接（`login/index.vue:122-130`）——即**间接路径**，而非探市页本身。
- 结论：需要**新增登录态感知**：已登录 → 探市「添加观察」改为引导跳转自选页（或直接写后端自选）；未登录 → 保留匿名 localStorage 模式 + 注册 CTA（#808 转化区可补回）。

### 2.4 问题 4：点击 logo 不跳主站 —— 属实

- `MarketHeader/index.vue:12-16` logo 区（`BrandLogo` + 文本 + badge）**无 click 事件、非 router-link、无 cursor:pointer**。
- 对比主站 `SidebarLogo` 有跳转逻辑。修复：logo 区加点击 → 已登录跳 `/welcome`，未登录跳 `/explore`（或首页 `/`）。

### 2.5 问题 5：风格归一化 —— 探市/温度计已统一，缺主站衔接

- 探市（`explore/index.vue:5`）与温度计（`temperature/index.vue:5`）已共用同一 `MarketHeader` + `useMarketHeaderNavs()`（探市/温度计/自选三 nav）——**内部已归一**。
- 断点：探市是独立全屏路由（`remaining.ts:33-42`，不经过主站 Layout），主站是 pure-admin Layout（`layout/index.vue`，lay-navbar 面包屑+头像）。两者视觉语言同源（同一 token），但**导航体系不衔接**：探市 header 无登录态、无头像、无返回主站入口。
- 归一化方向（待讨论）：探市 header 增加登录态（未登录：登录/注册按钮；已登录：头像下拉或「进入主站」）；logo 点击衔接；「自选」nav 未登录时点击可弹登录引导而非直接踢走。

---

## 3. 探市 vs 自选 区分度（产品目的推导）

| 维度 | 探市 `/explore` | 自选 `/watchlist`（主站） |
|---|---|---|
| 定位 | **市场上下文 + 漏斗顶端**（免登录试用） | **个人资产管理**（登录拥有） |
| 数据 | 市场温度/指数/板块 + 本地观察草稿 | watchlist 表（后端权威，family 隔离） |
| 核心动作 | 浏览 → 添加观察（钩子） → 注册 | 分组/标签/置顶/实时行情/持仓联动/记账 |
| 数据归宿 | localStorage 草稿（未登录） | 后端 API（登录） |
| 关键衔接 | 注册后数据迁入主站「观察仓」分组 | 观察仓 → 可晋升持仓/自定义分组 |

- 基估宝**没有登录墙**（全部 localStorage，云同步可选）——它的「自选/分组/持仓」一体，无「探市 vs 自选」之分。
- fundmate 的价值在于**记账体系**（XIRR/组合/清仓分析/导入）远超基估宝；基估宝可借鉴的是**工具体验**（轻、快、实时、本地持久化细节）。
- 区分度结论（延续 U1 D5-D7）：一套自选、两个入口；探市是「观察中」（扁平、无分组），主站是「观察仓」（归属、可分组、可晋升）。**差异化新增能力应往「估值深度 + 记账联动」方向走**（基估宝做不到的：估值×持仓盈亏、估值×清仓复盘）。

---

## 4. 基估宝功能参考评估（要 / 不要 / 待定）

### 4.1 要（低投入高价值，与探市/自选直接相关）

| # | 功能 | 借鉴点 | 落地方式（不抄代码，AGPL 红线） | 优先级 |
|---|---|---|---|---|
| 1 | 估值数据源多路 + 来源标识 | `valuationSource`/`DataSourceAccuracyBadge`：标注「官方估值/搜狐/天天/兜底」 | 复用现有 `useRealtimeQuotes` 三级降级，增加来源字段 + UI 徽章（与 #807 风险横幅互补） | P1 |
| 2 | 估值分时曲线 | 盘中估值分时缓存 + 卡片内小图 | 新浪/腾讯分时接口（U1 §5.11 #2/#12），新增组件，数据无需云同步 | P2 |
| 3 | 折叠状态记忆 | `collapsedCodes` 等 3 类折叠 key | localStorage 记展开/收起，纯前端 | P1（顺手） |
| 4 | 视图切换 卡片/列表 | `viewMode` | 探市/自选表格已存在，移动端卡片列表（#808 §7 已有设计） | P2 |
| 5 | 数据导入导出（JSON 合并策略） | 按 key 合并去重（funds 按 code、transactions 按 id） | 我们已有交易导出（P2-15）；自选导出可加（watchlist.md §1.5.11 已规划） | P2 |
| 6 | 刷新频率自定义 + 手动刷新 | `refreshMs`（5s-300s） | 自选页已有开关；频率配置可加 | P3 |

### 4.2 待定（有价值，需产品决策/排期）

| # | 功能 | 分析 | 建议 |
|---|---|---|---|
| 7 | 每日收益日历（`MyEarningsCalendarPage`） | 基估宝亮点；我们有持仓+净值历史，数据可支撑；契合「涨红跌绿」收益可视化 | **推荐做**，落点：welcome 或自选页新 Tab（待定）；但基估宝是「估算收益」（用估值近似），我们要用**真实净值**，口径更硬 |
| 8 | 待净值交易（`pendingTrades`：3pm 后买入挂起，净值更新自动入账） | 我们有 `fund-confirm-dates/` 接口与导入静默回填，机制接近；可借鉴交互 | 登记远期（关联 P1-20 定时任务） |
| 9 | 定投计划（全局/分组 scope） | 我们有完整记账，做定投 = 生成计划+自动入账，能自闭环 | 登记远期（SPEC 未排期） |
| 10 | 云端同步交互（`localUpdatedAt` + 冲突弹窗选择） | P2-23 云同步引擎已排期（增量双向+LWW）；基估宝「冲突让用户选」可作补充交互 | 纳入 P2-23 设计参考 |
| 11 | OCR 截图导入 | U1 Phase 4/5 已设计（B3 合规约束已定） | 维持原计划 |
| 12 | 大盘指数可勾选 | 探市指数卡目前 3 个，基估宝可勾选多个 | 纳入探市 Phase 3 扩展（U1 §5.11 #8 全景） |
| 13 | 关联板块展示（基金→板块实时涨跌） | 需 `sector_fund_map` 种子（§10 已建结构未灌数据） | 待板块资金流数据源建设（tech-debt B5） |

### 4.3 不要（或明确不做）

| 项 | 原因 |
|---|---|
| 纯前端 JSONP 架构 / localStorage 为主库 | 我们前后端分离 + SQLite 权威（数据主权、合规） |
| 整团 JSON `user_configs` 表 | 我们规范化 `watchlist`/`positions`/`transactions` 建模 |
| CLI 工具 | 极客向，优先级低（远期可考虑 `jgb` 式查询脚本） |
| 捐赠弹窗 | 已有 `donate.md` 与落地页渠道 |
| 基金转换/分红方式模态框 | 记账域已有对应能力（分红全链路已实现），无新借鉴点 |
| QDII 估值、板块资金流 | U1 §10 已自研落地，无需借鉴 |
| 公告/更新日志/教程抽屉 | 与产品气质不符，过重 |

---

## 5. 探市/自选功能规划（建议排期，待讨论收敛）

### Phase A（修复 + 衔接，2-4 人天）

1. **修迁移桥**：`migrateExploreData` 改为调后端 `/api/watchlist/items/`（带 costPrice/quantity 透传 → 生成「观察仓」分组资产），**迁移成功前不删 localStorage**（失败保留）；迁移完成给 toast「已为你同步 N 个关注」；`showbuy_explore_migrated` 登出清理。
2. **探市登录态感知**：未登录 → 匿名观察模式 + 注册 CTA（可补回 #808 转化区）；已登录 → 「添加观察」改为跳转自选页（或直写后端），navs 增加「进入主站」。
3. **logo 点击跳转**：未登录 → 首页/探市，已登录 → `/welcome`。
4. 路由免登录策略统一（`/explore` 与 `/temperature` 同一写法）。

### Phase B（体验增强，3-5 人天）

5. 估值来源徽章 + 分时曲线（4.1 #1/#2）。
6. 折叠记忆 + 视图切换（4.1 #3/#4）。
7. 观察仓 → 持仓晋升交互（B5 合规：「仅关注，未记录持仓/成本」标注，引导升级）。

### Phase C（差异化，排期另定）

8. 每日收益日历（4.2 #7，真实净值口径）。
9. 自选导出（4.1 #5）。
10. 截图导入（维持 U1 Phase 4/5）。

---

## 6. 问题清单（本次发现的 bug / 缺口）

| # | 严重性 | 问题 | 证据 | 建议 |
|---|---|---|---|---|
| B1 | 🔴 高 | 探市登录迁移后本地数据被删且主站读不到（双端丢失） | `useSupabaseAuth.ts:76-81,106-107,135-143` + `api/watchlist.ts:128` + `models.py:16` | 改后端 API 迁移 + 删前确认 |
| B2 | 🔴 高 | 迁移丢弃 costPrice/quantity | `useSupabaseAuth.ts:137-143` | 透传字段 |
| B3 | 🟡 中 | 迁移无确认弹窗（#808 设计「强阻断询问」未实现） | `useSupabaseAuth.ts:76-81` | 补确认/预览 |
| B4 | 🟡 中 | `showbuy_explore_migrated` 登出残留，换账号不重迁 | `useSupabaseAuth.ts:84-87` | SIGNED_OUT 清理 |
| B5 | 🟡 中 | 探市页无任何登录态分支与注册 CTA（#808 转化区未实现） | grep 证据，`explore/index.vue:235` | Phase A-2 |
| B6 | 🟡 中 | logo 点击无跳转 | `MarketHeader/index.vue:12-16` | Phase A-3 |
| B7 | 🟡 中 | `/explore` 白名单 vs `/temperature` meta 两种免登录写法 | `remaining.ts:33-53`、`router/index.ts:122` | 统一 |
| B8 | 🟡 中 | localStorage key 沿用 V1 品牌 `showbuy_explore_v1` | `useLocalHoldings.ts:4` | 更名 + 兼容迁移 |
| B9 | 🟢 低 | 探市表格盈亏计算 `(price-cost)*qty` 直接 float 乘除，未走 Money 口径（前端展示域规范待确认） | `explore/index.vue:888-889` | 确认口径 |
| B10 | 🟢 低 | 探市与温度计同接口两套取数（explore 本地 ref vs temperature store） | `store/modules/temperature.ts` vs `explore/index.vue:545-695` | 合并到 store |
| B11 | 🟢 低 | `useLocalHoldings` 无跨 tab 同步（双 tab 互相覆盖） | `useLocalHoldings.ts:21-36` | storage 事件监听 |
| B12 | 🟢 低 | 上限提示文案「注册后可解锁更多」但注册后不解除 | `useLocalHoldings.ts:53` | 与登录态打通 |

---

## 7. 开放问题（待产品/技术讨论）

1. **迁移落点**：观察仓资产走后端 API 落 SQLite（现状后端权威）——是否等 P2-23 云同步再动？建议先修（当前是数据丢失 bug），云同步是增量改造。
2. **「添加观察」登录后行为**：a) 登录后探市不再能添加，跳自选页添加（用户提议）；b) 登录后仍可添加但直写后端。倾向 a（区分度清晰），待确认。
3. **每日收益日历**口径：真实净值（T+1 确认） vs 估值近似（当天）。基估宝用估算；我们建议真实净值，但当天无数据（需等净值发布）。
4. **探市 header 归一化程度**：仅加登录态按钮，还是整条 header 改为主站 lay-navbar 变体？倾向前者（保持探市轻量独立）。
5. **#808 转化区**是否补回（HERO CTA + 底部转化 + 损失厌恶文案）——与登录态改造一起做还是后置？
6. **观察仓分组**命名与位置：主站「观察仓」（is_system + group_type=observation）是否需要前端专门视图（当前主站自选页系统分组里是否有「观察仓」入口，需核对）。

## 8. 涉及文档（需同步更新）

> 2026-08-08 并行 triage 已更新 `roadmap.md` §1.2/§3 与 `watchlist.md` 顶部 tip：#807 更正为「实时估值核心(成功标准 1–7)已交付并关闭」，沙盒子系统 8–11 拆至 #821。与本文 §1.2 结论一致，无需再改。

- `docs/working-notes/explore-watchlist-replan-2026-08-08.md`（本文）
- 关联：issue #821（探市免登录沙盒子系统，成功标准 8–11）——本文 §5 Phase A 的「探市登录态感知」与 #821 范围有重叠，落地时需对齐边界
- U1 总纲（下载目录版）——建议本纪要收敛后将其收编进仓库 `docs/`（或归档），避免信息再分裂

---

## 9. 2026-08-09 追加：架构决策墙与付费/免费分层

> 触发：与用户逐条确认探市×自选后续规划（基估宝 PRO 调研、估值刷新频率、同步策略、付费分层）。所有决策已对齐。

### 9.1 估值刷新频率与前端直连（硬约束）

- **刷新频率**（用户纠正）：支持 **30s / 1m / 90s** 轮询选项，非「每日 1 次」；用户可自选。
- 由此得出**硬约束**：高频估值必须**前端直连行情源**——1000 用户 × 盘中 4 小时 × 每分钟轮询 ≈ **24 万次/天**，后端 API 承载不了（也是成本黑洞）。后端只做低频工作：最佳数据源统计、用量计数、开关下发。
- 这与 #807 `useRealtimeQuotes` 三级降级（官方 fundgz → 新浪 → 腾讯兜底）方向一致：**前端直连是既有架构**，确认保留并作为正式约束写入。
- Supabase 放高频数据是伪需求（§9.4 双库分工）：Supabase 只存用户账本（低频），行情走行情源前端直连。

### 9.2 估值开关（双层）

- **用户级**：前端 localStorage `showbuy_realtime_quotes_enabled`（`useRealtimeQuotes.ts` 已有）——已实现。
- **平台级**：后端 env `REALTIME_QUOTES_ENABLED` + 配置下发接口——当数据源压力过大或合规收紧时，后端可一键关闭全站估值，**无需发版**。
- 双层开关语义：平台级为总闸，用户级为个人偏好；平台级关闭时前端尊重总闸。

### 9.3 历史净值：按需回填，T 日不回填

- 录入/导入历史交易时，按需触发**单只基金全量回填**（实时接口，走 `--targets` 通道），**不做全市场全量**。
- **T 日净值不回填**（回填止于 T-1）：当日净值导入/回填用户看不到、心理打鼓，且盘中数据未定；此规则写入文档防再踩坑。
- 拒绝基估宝式「全量拉取」：数据量大、东财封 IP（`eastmoney-antiscrape-2026-08-05.md`），只按需。

### 9.4 双库定案：Supabase + Turso；Cloudflare D1 否决

- 现状：单 SQLite（`backend/invest.db` **868MB 实测**，910,417,920 B，2026-08-07 清理无效净值后）。
- 权威方案：`docs/backend-restructure-edgeone-dualengine.md`（2026-08-01）——用户域 → **Supabase**（免费层 500MB），市场域 → **Turso**（免费 9GB）。
- **Cloudflare D1（即「Cloud Code 里的 S2」）：否决**。原因：① 无 SQLAlchemy 方言（需 Legacy ORM 曲线救国且不兼容）；② 绑定 Workers/JS 生态（Python/Flask 主技术栈排斥）；③ 单线程写入、无交互事务。Turso（libsql）同族且更优，维持定案。
- Supabase 免费层冷启动问题：500MB 免费 + 停用 7 天暂停实例 → 保活方案见 `free-cloud-services-2026-08-09.md`（`supabase-keep-alive.yml` 已存在，每 6 天 ping `/auth/v1/settings`，不触东财，无 403 风险）。
- EdgeOne Pages Python 运行时原生支持 WSGI/APIFlask（零重写，双库文档 §7.1）；香港节点**只读不抓东财**（§14）；SCF 定时触发器无需备案（平台内部调度，无公网入站）。

### 9.5 同步策略：三入口 + full-sync 限范围 + DB 下载导入层

- 同步入口现状（`backend/app/tools/sync_metadata.py` + `sync_cli.py`）：
  - `--all`：日常增量（核心池 = 持仓 + 自选 + CSV，`fund_nav_job` 增量 N 天）；
  - `--full-sync`：全量，**仅限初始化/修复场景**——必须加范围限制（用户实测云端全量拉取很慢）；
  - `--targets / --target-file`：单只/CSV 定向（按需回填通道）。
- **DB 下载导入层**（用户决策，详见 `db-download-import-2026-08-09.md`）：初始化/迁移时用户下载预打包 DB 快照文件本地导入，**禁止云端全量拉取**。
- 抓取任务**禁止放 GitHub Actions**（美区 IP 被东财封，`eastmoney-antiscrape` 实证为出口 IP 级封禁）；过渡期用 Windows 任务计划程序 schtasks 跑增量。

### 9.6 付费/免费分层（定稿）

**判定准则**（写入 issue）：

1. 免费源 + 本地计算 + 无滥用风险 → **不限次免费**；
2. 有真实边际成本（API 计费）或独特价值 → **限次/付费候选**；
3. 免费→付费禁止（损失厌恶）；付费→免费允许（未来免费化仅调 quota）。

| 功能 | 归属 | 说明 |
|---|---|---|
| 核心记账、导入导出、探市、温度计、自选、每日收益日历 | 免费不限次 | 本地计算/免费源，零边际成本 |
| **持仓穿透** | **免费不限次** | 东财免费接口无压力；若未来数据源被收费再重评 |
| OCR 截图导入 | 付费候选 | 真 API 成本（火山 Ark），免费兜底 5 次/天 |
| 行业拥挤度 | 付费候选 | 特色功能 |
| 一键自动源 | 付费候选 | 特色功能（基估宝「一键自动源 (Pro)」实证） |

- 每日收益日历为免费功能（用户明确，不得收费）。
- **通用用量表**（拒绝每功能建表）：`user_usage(user_id, feature, period_date, count, quota, updated_at)`；feature 枚举（`ocr_import`、`scheduled_sync`、…）；通用接口 `GET /api/usage/{feature}`；配额可配置（env/表）。
- OCR 费用评估（Ark，doubao vision，seed 档 0.8/8 元每百万 tokens）：单次 ≈ 0.0037 元（600 in + 400 out）；1000 用户 × 5 次/天上限 ≈ 15 万次/月 ≈ **555 元/月顶格**；现实 20% 活跃 ≈ 74 元/月——**可承受**。免费 50 万 tokens 一次性额度 ≈ 仅 500 次，不够生产，只是试用。缓存命中 1.2 元/M 可省 80%（图省事可不用）。

### 9.7 基估宝 PRO 调研结论（2026-08-09，gh api 实证）

- **架构形态**：开源 main 分支自 2026-07-05 起转为「纯构建校验」分支（提交说明：移除在线自动部署，避免覆盖 pro 会员版线上站）→ **PRO 代码整体闭源**，仅运行于 fund.cc.cd。开源仓库无 stripe/paywall/billing 代码。
- **PRO 版本时间线**（release 实证，`hzm0321/real-time-fund`）：
  - v2.4.0-pro（07-05）：小贴士、PC 表格顶部滚动条、自选分组排序、指数个性化设置
  - v2.4.1-pro（07-07）：发布官网 fund.cc.cd/home、@jigubao/cli、关联持仓「定/待」标签、修复分组迁移数据丢失
  - v2.4.2-pro（07-13）：关联板块板块主题切换、OCR 识别结果二次修改、数据源列右对齐
  - v2.5.0-pro（07-14）：实时板块资金流向、优化关联板块数据刷新
  - v2.5.1-pro（07-15）：修复净值获取接口失效
  - v2.5.2-pro（07-17）：更换前 10 重仓接口方案、PC 滚动条样式
  - v2.5.3-pro（07-21）：更换数据源接口方案、优化 OCR 识别方案、市场指数卡片布局
  - v2.5.4-pro（07-22）：数据源需登录才可访问、部分基金时间最小单位仅日级
  - v2.6.0-pro（07-23）：移动端下拉刷新、实时板块追踪本地记录、**「一键自动源 (Pro)」**、OCR 确认弹框选项本地记录
  - v2.6.1-pro（07-27）：**赞助回馈入口**（回赠赞助过的用户）、升级本地数据存储支持更大基金量、修复东证指数接口
  - v2.7.1-pro（08-05）：**账号密码登录**、设置弹框布局优化、接口缓存优化
- **商业模式推断**：开源版 = 裁剪引流「限免层」（v2.1.0 普通用户 OCR 限次、v2.2.1 昨最准/昨误差限免、v2.3.0 自动切源限免）；PRO = **赞助制会员**（非订阅，v2.6.1-pro 赞助回馈佐证）解锁进阶能力。与我们「免费限次 + 付费解锁」同构——**OCR 限次得到竞品实证**。
- **借鉴动作**：① 一键自动源/数据源准确性统计 → 付费候选（§9.6）；② 每日收益日历免费（§9.6）；③ OCR 限次设计被实证支持。

### 9.8 产出物

- 本纪要（§9 决策墙）。
- `docs/working-notes/free-cloud-services-2026-08-09.md`：免费云服务清单（内部）。
- `docs/working-notes/db-download-import-2026-08-09.md`：DB 下载导入层设计（内部）。
- 6 个 issue：① 探市登录态+收藏快捷方式 ② 迁移桥修复+双层估值开关 ③ OCR 截图导入+通用用量表 ④ 按需回填+T 日不回填+sync 入口职责 ⑤ DB 下载导入层 ⑥ 付费/免费分层落地。

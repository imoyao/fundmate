# fundfof 详情页「怎么实现的」· 技术调研（#1973）

> 日期：2026-10-10　性质：**纯调研卡，不含实现代码**（#1973 验收明确要求）
> 上级：#1962（B2 子卡）　设计依据：`product-detail-page-design-2026-10-08.md` §9.1 / §10
> 前两轮：`fundfof-gap-analysis-2026-09-30.md`（有什么、缺什么）·
> `fundfof-round2-db-issue-2026-09-30.md`（真库实证、缺口在自建）
> **本轮补的正是前两轮缺的那一格：它怎么做的。**

---

## 0. 结论先行

**① fundfof 的 13 个 tab 没有一个「重实现」，全是同一个骨架换参数。**
反编译实证：13 个 tab 共 30 个组件，**每个组件只发1–4 个 GET、只渲染 1–4 张图**。
它的复杂度不在前端，在**后端预计算 + 一堆独立派生表**（`excess-return` / `scenario-analysis` /
`style-monitoring` / `position-monitoring-hot` …）。前端薄得像一张白纸。

**② 它的「13 tab」实际只有 4 类东西，我们已经全有了。**
把 30 个组件按端点归类，去重后**只剩 8 个数据家族**：

| # | 数据家族 | 覆盖 tab | 我们有没有 |
|---|---|---|---|
| F1 | 净值序列 | 业绩表现 / 相似走势 / 超额观察 / 相关性 | ✅ `daily_worth` 754万行 |
| F2 | 区间收益率（年/季/月/周） | 业绩表现 / 超额观察 | ✅ `services/performance` |
| F3 | 持仓明细（单期 or 多期） | 持股分析 / 调仓跟踪 / 言行一致 | ⚠️ 有，但**每只基金只有 1 期** |
| F4 | 行业配置 | 行业分析 / 大类资产 | ⚠️ `fund_industry_allocs` 830 条，仅 1 期为主 |
| F5 | 基准指数日线 | 超额观察 / 业绩归因 / 相关性 | ✅ **已补上**（`000300.SH` 5,223 条）|
| F6 | 规模 / 经理 / 费率 | 业绩表现 / 言行一致 | ⚠️ 部分（经理字段全空）|
| F7 | 派生统计（回撤/胜率/情景/风格） | 新高观察 / 情景适应 / 超额观察 | ❌ 需自建算法 |
| F8 | 概念 / ETF 资金流 | 概念含量 / ETF资金 | ❌ 无此数据源 |

**③ 因此「照抄 / 不做」的真正分界线不是 tab 名，而是「有没有 F7 派生统计」。**
13 个 tab 里，**能直接照抄的是 6 个**（业绩表现 / 相似走势 / 持股分析 / 行业分析 / 新高观察 / 相关性），
**需要先自建算法的是 3 个**（超额观察 / 情景适应 / 业绩归因），
**明确不做的是 4 个**（言行一致 / 调仓跟踪 / 大类资产 / ETF资金 + 概念含量）——理由见 §5。

**④ 有一条旧结论必须修正（重要）。**
`external-source-policy-2026-09-30.md` §0.1 与 round2 文档都写「沪深300 = 0 条，基准日线是阻塞点」。
**真库实测（2026-10-10）这条已经过期**：`index_daily` 现 **113,143 行 / 22 个指数**，
`000300.SH` 5,223 条（2005-04-08 ~ 2026-10-09）、`000905.SH` 4,794 条。
→ **「超额观察 / 业绩归因」的最大物理障碍已解除**，只剩 F7 算法自建。

**⑤ 接第三方源的判断：维持「不新增 fundfof 抓取」，且本文给出比 policy 更硬的理由。**
13 个 tab 用的**全部是它自己的库表**，前端没有任何一处直接调外部行情源。
也就是说：**照抄它的界面不需要碰它的数据**，更不需要接第三方。本卡没有任何动作需要动policy 的红线。

---

## 1. 取证方法（可复现）

| 材料 | 获取方式 | 强度 |
|---|---|---|
| 主 bundle `https://www.fundfof.com/assets/index-CiIF97mf.js` | `curl` 直取，3,799,519 字节 | 源码实证 |
| tab 白名单 | bundle 内`["业绩表现",…]` 字面量（3 处：路由校验 / 切换逻辑 / 过滤） | 源码实证 |
| tab → 组件 → 端点映射 | **花括号配对定位组件函数体**，只在函数体内提取 `/api/*`（见 §1.1） | 源码实证 |
| 我方数据 | 真库只读直连 `file:…invest.db?mode=ro` | 真库实证 |
| 我方代码 | `backend/app/domains/*/views.py` 端点清点 + `frontend/src/views/product/` 区块清点 | 代码实证 |

### 1.1 为什么必须用花括号配对（前两轮的坑，本轮修正）

第一轮提取 tab 端点时用「关键词 ±3KB 窗口」，**相邻 tab 的端点会被串进来**
（例：「超高观察」窗口里混进了「相似走势」的 `nav-history`）。
第二版改用「切到下一个 tab 分支」，**遇到组件定义点就失效**——bundle 是**单行**压缩代码，
行首锚点（`^var`）只匹配到 1 处。

**正确做法**：`SYM=function(...){` 正则定位定义 → 从其后第一个 `{` 起做配对扫描
（跳过字符串 / 模板串 / 行注释 / 块注释）→ 只在该函数体内提取端点。
修正后 30 个组件**无一串扰**，每个组件恰好 1–4 个端点，与人工阅读代码一致。

**反向验证（已跑，结论保留）**：把两种方法并排跑同一批 27 个组件，
窗口法**6 个组件串扰**（`I5e` / `R5e` / `F5e` / `jSe` / `NSe` / `fSe`），
且**串扰方向全部是「相邻组件的端点漏进来」**——例如 `F5e`（相关性/相近基金）
被塞进 `style-monitoring`（实属调仓跟踪）、`jSe`（情景适应）被塞进 `year-high`（实属新高观察）。
这类错误**不会让脚本报错**，只会让表格看起来很正常，然后让排期基于错的依赖。
⇒ **这正是本文 §2 的端点表可信、而「窗口法版本」不可信的原因。**

### 1.2 bundle 已整体内联，**无动态 chunk**

`import("./xxx")` 命中 **0** 次，`__vite__mapDeps` 0 次 ⇒ 整个前端（含 ECharts、axios、
React 18.3.1）打进**单个 3.8MB 文件**。

**对我们的意义**：fundfof 没有做代码分割，我们**不应该照抄这一点**。
我方前端是 Vite + 路由级懒加载，详情页新增 8 个区块时应保持懒加载，
别把 ECharts 拉进首屏 bundle（我方已有 `echarts` 按需引入的既有实践，以现有配置为准）。

---

## 2. 完整 tab → 实现映射（13/13，全部实证）

`pe = "//www.fundfof.com"`（**同源相对路径**，前端与API 同域，前端不跨域）。
每个 tab 的组件在 `useEffect(..., [e, s])` 里按 tab 切换懒加载，**首屏只请求当前 tab**。

| # | tab | 组件 | 端点（函数体内实证） | 图表形态 |
|---|---|---|---|---|
| 1 | **业绩表现** | `XO` / `b4e` / `N4e` / `j4e` / `k4e` | `nav-history`、`yield-year`、`yield-quarter`、`yield-month`、`statistics-roll`、`ulcer-index/{code}` | 净值折线 + 年/季/月收益柱 + 滚动统计 + **溃疡指数**表 |
| 2 | **相似走势** | `u4e` | `nav-history`、`similar-patterns` | 净值曲线叠加对比 |
| 3 | **言行一致** | `H5e` | `manager-consistency`、`manager-report-content` | 经理口径 vs 实际持仓偏离 |
| 4 | **大类资产** | `oSe` / `w4e` | `asset-allocation-history`、`heavily-ratio`、`industry-change`、`industry-weight-distribution`、`report-dates`、`stock-holding-history` | 资产分布 + 重仓集中度 + 权重分布 + 行业变化 |
| 5 | **行业分析** | `cSe` / `uSe` | `industry-weight-distribution`、`industry-change`、`report-dates` | 权重分布饼图 + 跨期行业变化 |
| 6 | **持股分析** | `dSe` | （组件本身不发请求，数据由容器 `portfolio` + `report-list` 注入） | 持仓明细表 + 相似重仓基金 |
| 7 | **超额观察** | `_4e`/`gSe`/`fSe`/`wSe`/`pSe`/`vSe` | `excess-win-rate`、`excess-return`、`monthly-excess-return`、`quarterly-excess-return`、`weekly-excess-return` + `indexes/compare/{search,quote}` | 超额胜率 + 年/季/月/周超额柱|
| 8 | **调仓跟踪** | `A5e`/`I5e`/`L5e`/`R5e` | `net-value-tracking`、`position-monitoring-hot`、`position-monitoring-sw`、`micro-disk-insight`、`style-monitoring` | 净值跟踪 + 仓位监控（申万口径 `hot`/`sw`）+ 微盘透视 + 风格监控 |
| 9 | **新高观察** | `kSe` / `NSe` | `continue-high-low`、`year-high` | 新高统计 + 年度新高榜 |
| 10 | **相关性** | `F5e` / `M5e` | `similar-funds`、`similar-funds-nav`、`low-corr-funds`、`correlation`、`investment-type` | 相近基金 + ETF 相关性 |
| 11 | **情景适应** | `jSe` | `scenario-analysis`、`scenario-time-ranges` | 情景分析（多时间窗） |
| 12 | **业绩归因** | `P5e` | `performance-attribution`、`performance-attribution-years`、`attribution-credibility`、`index-returns` | 归因表 + **归因可信度** |
| 13 | **ETF资金** | （`useEffect` 内联） | `etf-net-inflow-history/{code}?time_range=` | 资金净流入时间序列（1月/3月/6月/1年/3年/5年/今年/成立来）|
| 动态 | **概念含量** | （`useEffect` 内联） | `fund-concept-holdings/{code}` | 概念板块权重 |

### 2.1 容器级共用接口（与 tab 无关，进入页面就发）

实证（容器 `v4e` 及其引用的 hook）：

| 端点 | 触发时机 | 用途 |
|---|---|---|
| `/api/funds/{code}` | 首屏 | 基金基础信息 |
| `/api/fund-type/{code}` | 首屏 | 判定品类（`ETF资金` tab 仅 ETF 可见）|
| `/api/ulcer-index/{code}` | **仅 `业绩表现` tab** | 溃疡指数 + 宽基列表 + 经理年限 |
| `/api/funds/{code}/valuation?start_date=&big_freq=Q\|HY` | `业绩表现` tab，`big_freq` 由「重仓/HY」开关切换 | 估值带（PE/PB），走 `indexes/compare/search` |
| `/api/funds/{code}/market-cap-distribution?holding_source_id=` | 持仓 tab | 市值分布（重仓/全量双口径）|
| `/api/funds/{code}/analysis-reports` + `/api/para-section-id?para_type=19&para_sub_type=3..8` | `行业分析` / `持股分析` tab | **AI 文字报告**：先取报告列表，再按 `para_type=19` 的 6 个子类型逐个取文案 |
| `/api/funds/{code}/report-list` | `持股分析` tab | 报告期列表，取 `report_date` + `holding_source_id` 驱动全tab 联动 |

### 2.2 首屏调用顺序（实证结论）

```
路由进入 (?tab=xxx)
  ├─ useEffect: fund_detail_view 埋点（sessionId::fundCode 去重，同一只不重复埋）
  ├─ 首屏: GET /api/funds/{code}  +  GET /api/fund-type/{code}
  └─ useEffect(依赖 tab): 只有当前 tab 的组件发请求（切 tab 才发，不预取）
```

**三条可直接照抄的工程做法：**

1. **tab 状态同步到 URL query**（`?tab=业绩归因`），并在导航列表里做白名单校验
   （`W.includes(Pe) ? Pe : "业绩表现"`）—— 非法值静默回落到首 tab，不抛错。
   → **我方照抄**：详情页各区块应同样支持 deep-link，刷新/分享后停在同一区块。
2. **切 tab 埋点带 `from_tab`**（`o` 用 `useRef` 存上一个 tab），
   并用 `sessionId::fundCode` Set 做「同一次会话同一只基金只埋一次首访」。
3. **切 tab 后自动滚到对应区块标题**：`document.querySelectorAll(".tab-content-title")`
   找视口内第一个标题，`window.scrollTo({behavior:"smooth"})`。→ 我方区块增多后同样需要。

---

## 3. 图表与依赖（照抄的可行性 + 不能照抄的地方）

| 项 | fundfof 做法 | 照抄判断 |
|---|---|---|
| 图表库 | **ECharts 全量内联**（大小写不敏感命中 39 处，含 boxplot / geo / dataset） | ⚠️ **不照抄内联方式**，但**照抄选型** |
| 图形能力 | boxplot（收益分布）、geo（地图）、dataset 转换（`echarts:boxplot`） | ✅ 值得看，我方 ECharts 已具备 |
| React 运行时 | React 18.3.1 + 手写 `jsx` 调用（**无 JSX 编译产物可读性**） | ❌ 不照抄 |
| 状态管理 | **zustand + persist，但只有 1 个 store：`theme-storage`** | ⚠️ 说明**它几乎没有全局状态**，13 tab 无共享 store |
| 数据请求 | axios 存在但**详情页全用原生 `fetch` + `.json()`** | ⚠️ 无请求层、无统一错误处理 |
| 组件分割 | `React.lazy` **0 次**、`Suspense` 11 次（但无 lazy 配对）| ❌ 不照抄 |
| 加载态 | `加载中…` 107 处、`暂无数据` 65 处、`animate-pulse` 18 处（Tailwind 自绘骨架）| ✅ 照抄「每区块独立 loading，不做全页遮罩」 |
| 错误态 | `catch → console.error → 保持空态`，`加载失败` 33 处 | ✅ 照抄降级哲学，⚠️ 但它把错误只打console，用户侧看不出「数据没来」 |
| 超时/重试 | 详情页**无 AbortController、无重试**（bundle 里那 9 处 AbortController 属其他模块）| ⚠️ 我方应**做得更好**，不照抄 |

**结论：它的前端工程水平一般（单文件 3.8MB、无代码分割、错误只打 console）。
值得抄的是「数据家族切分 + tab deep-link + 逐区块独立降级」这三件事，
不是它的工程实现。**

---

## 4. 我方数据可得性（真库只读实证，2026-10-10）

| 表 | 行数 | 对本卡的意义 |
|---|---|---|
| `daily_worth` | **7,546,977** | F1 ✅ 2001-12-18 ~ 2026-10-09，3,419 只基金 |
| `index_daily` | **113,143**（22 个指数） | F5 ✅ **已扩容**（见 §0④）|
| `fund_holdings` | 6,423 | F3 ⚠️ 101 只基金，**但期数分布 = 每只仅 1 期** |
| `fund_industry_allocs` | 830 | F4 ⚠️ 101 只，3 个报告期（2025Q4 / 2026Q1 / 2026Q2）|
| `money_fund_daily_worth` | 1,215,608 | 货基单独一张表（去重时别只查 `daily_worth`）|
| `securities` | 8,357 | ⚠️ `sector` 填充 **3/8357**（round2 写 0，现在 3 条，仍等于没有）|
| `managers` | 4,267 | F6 ⚠️ `appointment_date` **0**、`sum_scale` **0** |
| `fund_managers` | 34,812 | ⚠️ `start_date` **0**、`end_date` **0**（全在任，任期不可用）|
| `positions` 持仓池 | **142** 只标的 | 详情页的真实服务对象；其中 **103** 只有净值 |

### 4.1 关键缺口只有一条：持仓**期数**

```
fund_holdings 每只基金的期数分布： [(1, 101)]← 101 只基金，每只都只有 1 期
```

这一条直接否决了 **4 个 tab**：

- 调仓跟踪（需要两期以上对比）
- 大类资产（`asset-allocation-history` 是**历史序列**端点）
- 行业变化（`industry-change` 需要跨期）
- 相似走势（虽然只要净值，但要对比多只基金的形状，勉强可做）

**它不是「要新开数据源」，而是「让`fund_position_job` 多跑几个报告期」**——
round2 已实证：适配器、job、注册位全在，`sync_logs` 里 `fund_position` 记录数 = 0。
这是**排期问题，不是可行性问题**。

### 4.2 与旧文档冲突处（以本轮为准）

| 旧结论（09-30 / 10-01） | 本轮真库实测 | 处置 |
|---|---|---|
| `index_daily` 只 10 个 `.WI` 指数，沪深300 = **0** 条 | **22 个指数 / 113,143 行**，`000300.SH` **5,223** 条、`000905.SH` 4,794 条 | ❌ **撤回**。基准日线已补齐，「超额/归因」物理障碍解除 |
| `funds` 26,938 | 26,938 | ✅ 未变 |
| `fund_holdings` 6,423 / 101 只 | 6,423 / 101 只，**每只仅 1 期** | ⬆️ **精确化**：表不是问题，**期数**才是 |
| `securities.sector` 0 / 8,357 | **3** / 8,357 | ⬆️ 仍等于没有，无需行动 |
| `managers` 4,264 | 4,267 | ✅ 近似未变（+3 为日常同步）|

---

## 5.照抄 / 不做 清单（本卡核心交付）

### 5.1 ✅ 照抄（6 项）—— 有数据、有算法、无需新数据源

| tab / 能力 | 抄什么 | 我方支撑 | 归属 |
|---|---|---|---|
| **业绩表现** | 净值走势 + 年/季/月收益 + 滚动统计 + **溃疡指数** | `daily_worth` + XIRR 模块；`GET /api/products/fund-profile/` 已有 | 一期已有，补「滚动统计 + 溃疡」两块 |
| **相似走势** | 净值曲线叠加对比 | `daily_worth` | 低成本，直接可做 |
| **持股分析** | 持仓明细表 + 市值分布 + 报告期切换 | `fund_holdings`（单期够用）| 一期已有持仓区块，可加深 |
| **行业分析** | 行业权重分布 + 行业名单 | `fund_industry_allocs` 830 条 | 直接可做 |
| **新高观察** | 新高统计（当前处于历史什么位置） | `daily_worth` 现算，**纯算法无新数据** | **零成本，建议优先** |
| **相关性** | 相近基金（按持仓/收益相似度）+ 低相关基金 | `fund_holdings` + `daily_worth` | 直接可做 |

**tab 化本身也照抄**：13 个平铺 tab 是错的设计（用户 90% 只看 3 个）。
**我方按 §6 分期矩阵做成「首屏 3 区块 + 可折叠进阶」，不抄 13-tab 布局。**

### 5.2 ⚠️先自建算法，再谈照抄（3 项）

| tab | 需要什么 | 阻塞在哪 | 判断 |
|---|---|---|---|
| **超额观察** | 超额胜率 + 年/季/月/周超额 | 基准日线**已就绪** ✅；`funds.benchmark` 填充 3,101/26,938（11.5%，**持仓池内 88.7%**）| **可做**。缺的是基准映射 + 区间对齐算法，纯自建 |
| **业绩归因** | 归因表 + 可信度 | 同上；**归因需 Brinson 分解**，比超额高一档 | **可做但后置**，归因可信度（`attribution-credibility`）是其精华，值得单独研究 |
| **情景适应** | 情景分析（多时间窗） | 需要自建情景定义（涨/跌/震荡 → 该基金表现） | **性价比最低**，13 个 tab 里最花哨、最缺可解释性，**建议最后考虑或直接砍** |

### 5.3 ❌ 不做（4+1 项，附理由）

| tab | 不做的理由（逐条） |
|---|---|
| **言行一致** | 依赖 `manager-consistency`：**经理任职区间 + 观点文本**。我方 `managers.appointment_date` = **0/4,267**、`fund_managers.start_date` = **0**、观点文本压根没有。**这不是算法缺口，是要解季报 PDF**——远超本项目定位 |
| **调仓跟踪** | 依赖**持仓多期**（我方每只仅 1 期，见 §4.1）+ 申万口径仓位监控（`position-monitoring-hot/sw` 需申万行业分类逐期快照）。**成本高、用户价值低**：个人投资者不会按申万一级看自己那只基金的仓位 |
| **大类资产** | 依赖 `asset-allocation-history`（**股票/债券/现金/海外的跨期序列**）。我方**连单期大类资产表都没有**（只有 `fund_industry_allocs` 这一层行业配置）。要新开一条采集链路，收益是「一个饼图」 |
| **ETF资金** | 依赖 `etf-net-inflow-history`（**ETF 份额×净值推算的资金净流入**）。我方无此数据源，且**这只对 ETF 有意义**（fundfof 自己也只在 `fund_type==="ETF"` 时显示这个 tab）。规模小众 |
| **概念含量**（动态 tab） | 依赖 `fund-concept-holdings`（第三方概念板块归类）。**概念板块是玄学**，与本项目「抹平信息不对称」的定位冲突，且需外部概念源。**明确不做** |

---

## 6. 落地建议（不改代码，仅给排期）

**第0 优先级（零新数据，今天就能做）**
- 「新高观察」：纯 `daily_worth` 现算，无新数据源。
- tab deep-link（`?tab=` / `?section=`）+ 非法值静默回落 + 切区块埋点。**8 个区块后没有这个会很难用**。

**第 1 优先级（一次采集解锁多个能力）**
- 让 `fund_position_job` **回填多报告期**（不是新开链路，是让已有 job多跑几期）。
  解锁：行业变化 / 持仓重叠度 / 大类资产（部分）/ 调仓跟踪（部分）。
  **这是本卡识别出的最高杠杆单点。**

**第 2 优先级（纯算法）**
- 超额观察（基准映射 + 区间对齐）→ 业绩归因（Brinson）→ 二者共用 F5。

**建议开新卡的**
- 「持仓多期回填」独立卡（挂在 #870 后续，非本卡）。
- 「超额观察区块」卡（依赖基准映射表）。
- 「业绩归因区块」卡（依赖超额 + Brinson 实现）。

---

## 7. 对 `external-source-policy-2026-09-30.md` 的补充（**结论：无需改红线**）

policy §0.1 的「不新增 fundfof 抓取」结论**本文维持**，并补三条新证据：

1. **fundfof 前端不调任何外部行情源** —— 30 个组件全部 `fetch` 同源 `pe="/api/*"`。
   → **照抄它的界面不需要它的数据，更不需要接第三方源。** 本卡全程零第三方接入。
2. **§0.1 的「基准日线缺口」已消解**（§0④ / §4.2）——
   policy 里「剩下的两件事都在自建侧」这句话**结论不变但紧迫性下降**：
   基准日线已补齐，**只剩多期持仓**一件，且是排期问题不是来源问题。
   → 建议在 policy §0.1 加一行交叉引用本文 §4.2，**避免后来人按旧结论重复开卡**。
3. **`fundfof_crowding.py`（#1502）维持不扩大** —— 本卡未发现任何需要新增抓取的场景。

**建议改动**：policy **仅加一条交叉引用**，不改任何红线、不加新规则。

---

## 8. 诚实交代（未做到的事）

- **未做真机走查**：本文全部结论来自 bundle 源码静态反编译 + 我方真库只读，
  **没有用浏览器实际点开 13 个 tab**（fundfof 部分 tab 可能需登录，如 `/portfolio-penetration`）。
  静态反编译能拿到「发什么请求、渲染什么组件」，拿不到「视觉长什么样、排版好不好」。
- **未核对后端实现**：fundfof 的 `performance-attribution` / `scenario-analysis` 等端点
  **具体算法未知**（服务端闭源，前端只能看到入参出参）。
  §5.2 的「可做」判断基于**我方数据充分性**，不是「已知它的算法可复现」。
- **`Yt`（ETF资金组件符号）定义未定位**：该tab 的取数写在容器 `useEffect` 内联，
  已在 §2 表格按端点实证记录，但组件符号未还原（不影响结论）。
- **`dSe`（持股分析）组件内 0 端点**：数据由容器 `portfolio` + `report-list` 注入，
  已在表格中注明，**非提取失败**。

---

## 附：证据索引

| 内容 | 位置 |
|---|---|
| 主 bundle | `https://www.fundfof.com/assets/index-CiIF97mf.js`（3,799,519 B，2026-10-10 取）|
| tab 白名单字面量 | bundle 内 3 处（路由校验 `v4e` / 切换逻辑 / `ot` 过滤数组）|
| 组件端点提取脚本 | 花括号配对法，见本文 §1.1（**勿退回窗口法**）|
| 我方真库 | `file:D:/codes/fundmate/backend/invest.db?mode=ro`（**只读**）|
| 我方详情页区块 | `frontend/src/views/product/components/`（8 个，一期已合入）|
| 我方端点 | `backend/app/domains/products/views.py`（8 个：`resolve` / `fund-profile` / `stock-profile` / `manager-profile` / `advisor-profile` / `related-symbols` / `trend`）|

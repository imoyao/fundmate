# 探市 / 温度计页面收束评估 + #891/#892/#918 实证核查（2026-09-11）

> 性质：内部备忘（`docs/working-notes/` 全目录屏蔽出文档站构建，不对外）。
> 触发：issue #891 / #892 长期挂起、#918 待处置；用户提出「探市页与温度计页要不要合成一个页面」。
> 核查方式：读仓库代码 + 直查本地库 + 拉 GitHub Actions 失败日志 + 逐条比对历史文档。所有结论带 file:line 或命令级证据。
> 关联：`docs/spec/site-architecture-and-traffic-routing.md`、`docs/spec/launch-priority-baseline.md`、`docs/working-notes/explore-watchlist-replan-2026-08-08.md`（即 #893）、issue #808 / #821 / #891 / #892 / #893 / #918。

---

## 0. 结论先行（三条）

1. **数据链路断了，「基础数据不够」的直觉是对的，但根因不在算法。** 本地库温度数据停更于 **2026-08-02**（40 天前），`industry_crowding` **零行**；每日调度 workflow 自部署起**连续失败**（secrets 全空）。#891 / #892 的代码其实都已合入 dev —— 不是没写，是**没有数据流经它**。**这是当前最该修的一件事，且它比页面形态更阻塞上线。**
2. **探市页与温度计页应当收束，但收束 ≠ 简单合并。** 两页首屏共用同一份数据、同一批组件，探市的温度仪表盘是温度计的**真子集**；拆分的边际价值低。但探市页真正不可替代的是「观察列表 + 免登录漏斗」，不是那套重复的仪表盘。推荐**方案 D（单入口 + 概览/深度两档）**，兜底**方案 C（保留双页但去重）**。
3. **#918 的块 2 已完成、块 1 留了个会打挂 Vercel 构建的断裂、块 3 零进展。** 建议：新开卡承接「块 1 残留 + 块 3」，与 #918 双向关联后关闭 #918。

---

## 1. 探市页 vs 温度计页：事实基线

### 1.1 两页在做什么（逐段实证）

**探市 `/explore`**（`frontend/src/views/explore/index.vue` + 3 子组件）

| 区块 | 内容 | 组件 |
|---|---|---|
| Header | `MarketHeader` badge="探市"，navs = 探市 / 温度计 / 自选 | `MarketHeader` |
| 温度仪表盘 | L1：综合温度（hero，2 份宽）/ 恐惧贪婪 / 股债性价比<br>L2：市场情绪（且慢 / 有知有行 / 韭圈儿中长期）+ 估值指标（中位PB / 中位PE / 可转债）<br>L3：流动性（今成交额）+「行业拥挤度 →」「板块资金流 →」<br>指数快照：沪深300 / 中证500 / 创业板指 | `ExploreTemperatureDashboard.vue` |
| 添加/观察栏 | 仅未登录渲染 | `ExploreAddSection.vue` |
| 观察列表 | localStorage 本地存续 | `ExploreWatchlistTable.vue` |
| 转化区 | 未登录 → 注册 CTA；已登录 → 引导去自选页 | `index.vue:33-64` |
| Footer | 探市语系复盘引导 | `PageFooter` |

**温度计 `/temperature`**（`frontend/src/views/temperature/index.vue` + 3 子组件）

| 区块 | 内容 | 组件 |
|---|---|---|
| Header | `MarketHeader` badge="温度计"，同一套 navs | `MarketHeader` |
| 综合仪表盘 | 综合市场温度（`size="lg"` + `featured`）+ coreMetrics（恐惧贪婪 / 股债性价比 / 可转债 / 成交额） | `TemperatureGaugeCard` + `MetricCard` |
| 温度解读 | 等级 + 恐惧贪婪 + 短中长期 | `TemperatureContextCard` |
| 市场机会 | 由 store 的 `opportunityList` 渲染 | `SectionHeader` |
| 趋势图 | 30 / 90 / 180 天折线（echarts） | 页面内联 `chartOption` |
| 行业乖离度排行 | 表格 | `BiasTable.vue` |
| 行业拥挤度排行 | 表格（拥挤度 / 成交额占比 / 换手率 三列带进度条） | `CrowdingTable.vue` |
| 全部指标明细 | 紧凑表格 | `MetricDetailTable.vue` |
| Footer | 温度计语系复盘引导 | `PageFooter` |

**两页共用**：`MarketHeader`、`PageFooter`、`TemperatureGaugeCard`、`MetricCard`、`MetricGrid`、`SectionHeader`，以及**同一个数据 composable** `useTemperatureOverview()`（`composables/temperature/useTemperatureOverview.ts`，即 `/api/temperature/overview`）。路由侧两页均 `requiresAuth: false`（`router/modules/remaining.ts:52,63`）。

### 1.2 重叠度矩阵

| 指标 | 探市呈现 | 温度计呈现 | 同源 |
|---|---|---|---|
| 综合温度 | hero 卡（2 份宽） | `size="lg" featured` 大卡 | ✅ 同一 `composites.composite_temperature` |
| 恐惧贪婪 | L1 `MetricCard` | coreMetrics `MetricCard` | ✅ |
| 股债性价比 | L1 `MetricCard` | coreMetrics `MetricCard` | ✅ |
| 可转债 | L2 估值指标组 | coreMetrics | ✅ |
| 成交额 | L3 流动性大卡 | coreMetrics | ✅ |
| 且慢 / 有知有行 / 韭圈儿中长期 | L2 市场情绪组 3 卡 | `MetricDetailTable` | ✅ |
| 中位 PB / 中位 PE | L2 估值指标组 | `MetricDetailTable` | ✅ |
| 指数快照 | 独立一行（3 指数） | 无 | 探市独有 |
| 趋势图 / 乖离度表 / 拥挤度表 / 明细表 | 无 | 4 个区块 | 温度计独有 |
| 观察列表 / 添加栏 / 转化区 | 有 | 无 | 探市独有 |

**关键事实：探市页温度仪表盘里的每一张卡，在温度计页都有对应呈现。** 差异只在密度与排版，不在内容。

### 1.3 历史设计意图（文档回溯）

- `site-architecture-and-traffic-routing.md` §一：探市 = app 子路由（免登录沙盒），职责「研究页，引流到 app 转化」。
- `launch-priority-baseline.md` §一：硬指标并列写「**探市页可用**」+「**温度计页可用**」，是**两个独立验收项**。
- #893 §3「探市 vs 自选 区分度」：明确了「**一套自选、两个入口**」——注意，这里区分的是**探市 vs 自选**，**从未**论述过「探市 vs 温度计」的边界。
- 全仓检索（`docs/**/*.md`）**查不到**任何一条「探市与温度计为何拆成两页」的书面决策。
- 反向证据：探市页脚写「回看探市各指数与行业的口径」，温度计页脚写「可前往探市页查看指数快照与行业机会」——**两页页脚互相指路**，这是「本应是一页的两个 section」的典型特征。探市「综合温度」卡里还挂着「查看温度计 ›」跳转链接（`ExploreTemperatureDashboard.vue:178`），说明产品自己把温度计当作探市的**更深一层**，而非**另一个入口**。

---

## 2. 判据与结论

### 2.1 判据

判定「该不该拆两页」，不看两页长得像不像，看**每一页是否有不能被另一页承载的独立用户任务**。

- 温度计页的任务：**看市场冷热的完整画像**（趋势 + 行业维度）。
- 探市页的任务：① 看市场冷热；② 建立观察列表（漏斗）。

任务①与温度计页**完全重合**，不产生独立价值；任务②是独立价值，但它**不需要**靠一整套重复的温度仪表盘来承载 —— 观察列表自己就能撑起一屏。

### 2.2 结论

**拆分的边际价值低，应当收束。** 两页不是「同一件事的深浅两档」（第一直觉），而是「**同一份仪表盘的两种排版 + 一个探市独有模块**」。

### 2.3 但收束 ≠ 删掉一页

真正要回答的不是「要不要两个页面」，而是「**哪一份重复内容该被删掉**」。四个方案：

| 方案 | 做法 | 代价 / 风险 | 与既有决策的冲突 | 「尽快收束」适配度 |
|---|---|---|---|---|
| **A 全合并** | 温度计内容并入探市，`/temperature` 重定向到 `/explore` | 探市首屏变重（趋势图 + 3 张表），漏斗页属性被冲淡 | 低 | 中 |
| **B 反向合并** | 探市并入温度计，`/explore` 重定向到 `/temperature` | 丢掉免登录沙盒 + 观察列表的漏斗定位 | **高**：与 #808 / #893 §3 / site-architecture §一 直接冲突 | 不可取 |
| **C 保留双页 + 去重** | 两页都在，探市首屏仪表盘精简为 1 行锚点，观察列表上位；导航改为层级关系 | 两页仍在，但不再「长得一样」；改动最小 | 无 | **高** |
| **D 单入口 + 两档视图**（推荐） | 只保留 `/explore`，页内 Tab：「概览」（现探市）/「深度」（现温度计表格区） | 需一次路由/导航收敛 | 低（`/explore` 仍是对外唯一入口，导流链不变） | 中 |

**推荐 D，兜底 C。** 理由：

1. D 直接回答「要不要两个页面」= 不要，同时**不丢任何功能**（两档内容都保留）。
2. 与 #917 站点架构不冲突：`/explore` 仍是导流链唯一入口，只是它现在能继续往下滚，而不是「跳到另一个同质页」。用户从概览切到深度，是**同一页面的信息展开**，认知成本远低于跨页跳转。
3. 落地成本可控：`ExploreTemperatureDashboard` / `BiasTable` / `CrowdingTable` / `MetricDetailTable` **都已经是独立组件**，主要是「搬 + 删 + 重定向」，不是重写。唯一需要新拆的是温度趋势图（目前内联在 `temperature/index.vue` 的 `chartOption`）。

### 2.4 一个反直觉但必须说清楚的点

**合并解决不了用户真正卡住的问题。**

「这个页面挂了很久、阻塞上线」的实测根因是三条，与页面结构无关：

1. **数据链路断了**（见 §3）—— 温度数据停更 40 天，行业拥挤度零数据。**不论合并与否，两页现在展示的都是 8-02 的旧数据 / 空表。**
2. **探市页两个深度入口是假的**：`ExploreTemperatureDashboard.vue:85-91` 的「行业拥挤度 →」「板块资金流 →」只弹 `ElMessage.info("功能开发中")`（#821 已登记、未闭环）。
3. **行业维度内容本身薄**：拥挤度只有 3 列且无数据；温度只有日频快照、无更新。

所以正确排序是：**先修数据链路 → 再定页面形态 → 再补维度**。把页面合并放在最前面，是在优化一个暂时不显示内容的外壳。

---

## 3. 新发现：温度计数据链路断点（比页面结构更致命）

三条独立证据链。

### 3.1 数据层：本地库温度数据停更 40 天，行业拥挤度零行

```
$ python -c "sqlite3 只读打开 backend/invest.db"
market_single_values : 54 行，max(collected_at) = 2026-08-02
market_composites    : 16 行，max(collected_at) = 2026-08-01
market_multi_items   :  1 行，max(collected_at) = 2026-08-02
   └─ group by source → [('bias', 1, '2026-08-02')]
```

- `market_multi_items` **全表只有 1 行**，且 `source='bias'`；`industry_crowding` **一行都没有**。
- `market_single_values` 最新一条是 2026-08-02 的 `eastmoney_volume=25600.9`。
- 结论：**探市 / 温度计两页当前展示的是 2026-08-02 的快照；行业拥挤度表 100% 空表**（前端会走到 `CrowdingTable.vue:184` 的「数据暂不可用」空状态）。

### 3.2 调度层：每日调度 workflow 自部署起连续失败

```
$ gh run list --workflow=daily-snapshot.yml
2026-09-10T19:19:43Z  completed/failure  main
2026-09-09T19:33:03Z  completed/failure  main
2026-09-08T19:39:04Z  completed/failure  main
2026-09-07T20:15:47Z  completed/failure  main
2026-09-06T18:43:53Z  completed/failure  main
2026-09-05T18:39:49Z  completed/failure  main
2026-09-04T19:12:19Z  completed/failure  main
（此前 10 条内亦全部 failure）
```

失败日志根因（run 34519744964）：

```
env:
  DATABASE_URL:                 ← 空
  SUPABASE_DATABASE_URL:        ← 空
  SUPABASE_SERVICE_ROLE_KEY:    ← 空
  APP_ENV:                      ← 空
...
File "backend/app/core/db_factory.py", line 237, in build
    engine = create_engine(
sqlalchemy.exc.ArgumentError: Could not parse SQLAlchemy URL from given URL string
##[error]Process completed with exit code 1.
```

**secrets 全空 → 引擎建不起来 → 进程 1 秒即崩。** 且该 workflow 跑在 **`main`** 分支，而 `main` 长期落后 dev（见 `.workbuddy/memory/MEMORY.md` 长期断点）。

### 3.3 无任何兜底调度

- `.github/workflows/` 9 个 workflow，**没有任何一个**执行 `temperature` / `sync_cli` / `grab.*`。
- 自 schedule 的 5 个 workflow 中，`daily-snapshot.yml` 是唯一跑同步的，且失败。
- 本机 `schtasks` 查询无 fundmate / showbuy / temperature / sync 相关计划任务。
- `backend/app/tools/scheduler.py` 存在且 `temperature` job 已注册进 `orchestrator.py:158`，但**外部触发设施从未成功运行过**。

### 3.4 连带结论

- 用户「基础数据还不够」的判断**在数据层完全正确**，但它不是「算法没写完」——#891 / #892 的代码都在 dev 上（见 §4）。**是管道没通。**
- 抢修优先级应高于页面合并：**修 `daily-snapshot.yml` secrets + 把调度跑在 dev 分支 + 手动触发一次全量回填**，才是解锁这两页展示的前提。

---

## 4. #891 / #892 重新定位

| 卡 | 代码状态（实证） | 数据状态 | 建议 |
|---|---|---|---|
| #892<br>多维升级 | ✅ **全链路已在 dev**：`industry_crowding.py:528` `_em_amount_rank()` 出 `amount_pct` / `amount_pct_rank`；`:543` `_turnover_rank()` 出 `turnover` / `turnover_rank`；`:565` `_em_two_dim()` 合并；`:742-752` 写入 `data`。前端 `CrowdingTable.vue:72-135` 已有「成交额占比」「换手率」两列（带进度条）。CacheService 薄接口 PR #1379 已 merged（2026-09-10）。**5 项验收标准可逐条勾选。** | ❌ 零数据 | 代码侧可关；数据侧转新卡 |
| #891<br>baostock 分母兜底 | ✅ `industry_crowding.py:165` `_baostock_market_median_pb()` 已实现，接入 `market_pb_series()` 第三级兜底（legulegu → 缓存 → baostock → 东财 → 标灰），含线程超时保护。 | ❌ 零数据；且原卡自述 baostock 服务器本机不可达 | 同上 |

**与原方案的偏离（#892 已记录，此处复核确认）**：原设计指定复用 legulegu 的 `sw-congestion` / `sw-amount-ratio`，实测为 **VIP 接口、免费 token 取不到数据**（`industry_crowding.py:334` 附近注释），实现改为东财 `push2his` K 线自算。功能等价、数据源不同。

**给用户的直接回答**：这两张卡的待办不是写代码，是**让 job 跑起来并落库**。代码层已完成，数据层为零 —— 这正是它们「挂很久」的观感来源。

---

## 5. #918 实证核查与处置

| 块 | 内容 | 状态 | 证据 |
|---|---|---|---|
| 块 1 | 应用站落地页构建链退役 | 🟡 基本完成，**留了一个断裂** | 根 `package.json` 已无 `build:landing` / `build:about` / `build:story` / `build:pages` 四条脚本（PR #1326）；根 `landing.html` 已删；`AGENTS.md` / `tech-debt.md` 引用已更新。**但**：<br>① `vercel.json:3` 仍是 `"build": "pnpm run build:landing"` —— 该脚本已不存在 → **Vercel 构建必失败**（比清理前更坏：以前脚本在、只是 `readFileSync` ENOENT；现在脚本都没了）；<br>② `scripts/build-landing.mjs`（14,371 B）仍在仓库，成为孤儿；<br>③ `AGENTS.md:286` 仍写着「落地页：`pnpm run build:landing` / …」（已过期）。 |
| 块 2 | 导入页平台 logo 卡片 | ✅ **完成** | PR #1325 merged 2026-09-05 16:55（`feat(import): 导入页新增「支持导入来源」平台 logo 卡片区`）；`frontend/public/logos/` 7 个 SVG 在位。 |
| 块 3 | 三平台部署配置（EdgeOne / Cloudflare / Vercel） | ❌ **零进展** | `vercel.json` 无 `rootDirectory` / `outputDirectory`，`routes` 是 `404.html` 兜底（**不是 SPA 的 `index.html` 回退**）→ history 模式深链必 404；无 `wrangler.toml`；无 `netlify.toml`；应用站无 `<meta name="robots" content="noindex">`。 |

**回答用户的问句**「除了三平台部署配置之外，其他的问题是不是解决了？」：

- 块 2 **解决了**；
- 块 1 **基本解决，但留了个会直接打挂 Vercel 构建的尾巴** —— 而这条尾巴按 #918 自己的 2026-09-02 评论，本就划归「块 3 三平台部署重定处理」，不构成块 1 未闭环。

**处置建议**（用户已授权）：新开一张卡承接「块 1 残留 + 块 3」（二者都动 `vercel.json`，拆开反而会互相撞车），在 #918 与新卡上双向评论关联，然后关闭 #918。理由符合 AGENTS.md「部分完成时拆卡转移」与「Issue 原子化约束」（#918 本身就是三件事混装一卡）。

---

## 6. 参考基准（见基行事 fundfof.com）：借鉴什么、不借鉴什么

> 数据可抓取性分析见用户下载目录 `fundfof_crowding_analysis_20260909/fundfof_analysis.md`（该报告已给出「可抓但不应依赖」的结论，本文不重复）。

### 6.1 可借鉴（形态层）

1. **顶部「汇总卡」给出可行动结论**：平均拥挤度 8.4 / 拥挤（≥80）0 个 / 变化活跃 17 个 / 领涨赛道 光通信 20.3%。→ 我们首屏只有「值 + 档位」，缺「这一堆数字说明了什么」。
2. **表头按维度分组配色 + 每列独立百分位条**：拥挤度组 / 成交额组 / 换手率组… → 我们 `CrowdingTable.vue` 已是「数值 + 进度条」结构，但列少、无分组语义。
3. **表尾常驻「指标说明 + 百分位口径说明」**：→ 我们已有 footer 来源条，可扩出「指标说明」一块。
4. **ETF 趋势信号页的信号卡片网格**（每标的一卡 + 信号标签 + 关键指标）→ 可用于未来「行业/ETF 信号」视图，但**不是本期收束范围**。

### 6.2 不借鉴（风格层）

- 浅紫 / 浅绿多色 tag、彩色表头、emoji 图例（🟢🔴🟡）→ 与 `frontend/design.md` 的「**禁止 Emoji**」「**不用颜色作为唯一信息载体**」「**禁止硬编码 hex**」直接冲突。我们的温度语义色走 `--temp-low / --temp-mid / --temp-high`（与涨跌色物理隔离）。
- 其「综合拥挤度 0-100 加权合成」→ #892 已决策**不硬造合成公式**（市场无公认加权法），保持多维并列。**这个决策我认可，不因竞品有合成分就改。**
- 其顶层 stat 卡的视觉（大数字 + 圆角色块）与我们 `MetricCard` 同构，可直接用现有组件实现，无需新样式。

### 6.3 合法边界

- `/api/market/crowding/indicators` 的 9 个指标 label / 口径，可作**自研口径的对照基准**（开发期内部校验，**不落库、不展示、不接前端**）。
- 其拥挤度数据**不可作生产数据源**（无 SLA、CORS 可收紧、schema 可改、法律风险），此结论沿用原调研报告。

---

## 7. 关于调用其 LLM（`/api/market/llm-analysis`）：我的立场

用户设想：调用其 LLM 能力引入我们网站，且「不暴露我们的网站、让他们找不到是我们在调用」。

### 7.1 技术现实（逐条）

| 设想 | 现实 |
|---|---|
| 「匿名可调」 | 属实（实测 200，CORS `*`）。 |
| 「不暴露」 | **做不到。** ① 前端直连：浏览器必带 `Origin` / `Referer`（我们的域名），对方服务端日志一望即知；② 后端代理：能消掉 `Origin` / `Referer`，但**我们服务器的固定 IP 会暴露**，且对方可按 IP 封禁。**「让他们找不到是我们在调用」在技术上不存在**，代理只能提高门槛、不能消除。 |
| 免费无限 | 当前未观测限流 ≠ 以后没有；无 SLA、无版本化、无 changelog。 |

### 7.2 合规现实

原调研报告已定调：`crowding composite` 是竞品算法 IP，`llm-analysis` 是其**内容产出**。匿名可读 **≠** 授权商用；直接搬运展示 = 违反其 ToS + 触及《反不正当竞争法》互联网专条。

### 7.3 建议（按优先级）

1. **自建 AI 点评（推荐）**。平台已有 `ARK_MODEL=doubao-seed-2-1-pro-260628`（火山 Ark，二鸟说自动化在用）。用**我们自己的数据**（温度 / 拥挤度 / 乖离度 / 指数快照）喂**我们自己的模型**，产出「市场温度日报 / 赛道解读」。合规、可控、可缓存、可离线跑，且是差异化能力（对方的 LLM 内容对我们是黑盒，且其视角是「板块聚类 + 产业链传导」，与我们的「个人资产视角」调性不同，照搬等于替它背书算法）。
2. **仅内部对照**：把它的 `llm-analysis` 当口径基准，开发期人工看，**不落库、不展示、不接前端**。成本极低，可以立即做。
3. **若坚持要接对方接口**：只能「后端定时抓取 + 落库 + 明确标注来源 + 仅内部参考不对外」——**法律风险仍在，我不建议**。

---

## 8. 落地路径建议

### 8.1 排序（重要）

```
P0  修数据链路（§3）── 阻塞一切展示，与页面形态无关
P1  页面收束（§2，推荐方案 D / 兜底 C）
P2  #918 处置（§5）
P3  #891 / #892 数据侧收口（§4）
P4  维度扩展（拥挤度补 60线上 / 60日新高 / 融资 / 大单 —— 需先论证数据成本）
```

### 8.2 P1 方案 D 实施草图（约 2 人天，不含数据修复）

路由：`/explore` 保留为唯一入口（免登录白名单不变，D4 不变）；`/temperature` 重定向到 `/explore`（带 `?view=detail` 区分档位）。

页面：

```
/explore
├── MarketHeader（navs 收敛：行情 / 自选；去掉「探市 vs 温度计」二选一）
├── Tab「概览」（= 现探市）
│   ├── 汇总卡（新增：平均拥挤度 / 高温赛道数 / 活跃变化数 / 领涨赛道）
│   ├── 温度锚点一行（综合温度 + 恐惧贪婪 + 股债性价比）
│   ├── 指数快照
│   ├── 观察列表（漏斗主体，上位）
│   └── 转化 CTA
└── Tab「深度」（= 现温度计）
    ├── 温度解读 + 市场机会
    ├── 综合温度趋势（需从 temperature/index.vue 拆出组件）
    ├── 乖离度表 / 拥挤度表 / 明细表
    └── PageFooter（统一一份文案，去掉两页互指）
```

共用底部：`PageFooter` 单份，`revisitText` 不再出现「可前往探市页查看…」这类互相指路。

### 8.3 P1 兜底方案 C 实施草图（约 1 人天）

若暂不想动路由：

- 探市首屏仪表盘从「L1 + L2 + L3 + 指数快照」精简为「综合温度 + 恐惧贪婪 + 股债性价比 + 指数快照」（一屏内）。
- L2 市场情绪 3 卡 / L2 估值指标 3 卡 / L3 流动性大卡**移出探市页**（它们在温度计页 `MetricDetailTable` 已有更完整呈现）。
- 腾出的空间给观察列表，把漏斗做实。
- 导航语义从「并列入口」改为「层级关系」：探市页 header 的「温度计」改为「市场温度详情 →」。

---

## 9. 开放问题（待拍板）

1. **方案 D 还是 C？** D 是长期正解但动路由与导航；C 是当天能落地的去重。建议 D，若担心上线节奏则先 C 后 D。
2. **`/temperature` 的路由命运**：重定向（301）还是别名（alias）？影响外部已分享链接与 SEO（应用站 `noindex` 已定，SEO 影响有限）。
3. **观察列表是否升为概览档主位**？若升，探市页的「漏斗」属性会更强，但要重新排 L1 三卡的位置。
4. **数据链路抢修方式**：修 `daily-snapshot.yml` 的 secrets（需要你提供 Turso / Supabase 连接串），还是先在本机手工跑一次 `pdm run scheduler` 把本地库灌热（只解决开发环境）？两者不互斥，建议先跑本机验证链路通，再修 CI。
5. **调度应该跑在哪个分支**？现在跑 `main`（长期落后 dev），意味着即使 secrets 修好，跑的还是旧代码。是否改为 `dev`（或 `main` 先同步）？
6. **自建 AI 点评**是否立项？若立项，需要定：输入数据范围、产出形态（日报 / 卡片 / 赛道解读）、是落库还是实时生成、成本预算（火山 Ark 按 token 计）。
7. **拥挤度维度是否继续扩**（60 线上占比 / 60 日新高占比 / 融资买入占比 / 百万大单）？#892 原方案已明确「不做」的理由（逐成分股数千次请求不可承受 / 依赖 L2 付费源），若要做需重新论证数据成本（AGENTS.md 数据准入四问）。

---

## 10. 本次核查的原始证据清单

| 项 | 位置 / 命令 |
|---|---|
| 探市页结构 | `frontend/src/views/explore/index.vue`、`components/ExploreTemperatureDashboard.vue` |
| 温度计页结构 | `frontend/src/views/temperature/index.vue`、`components/{BiasTable,CrowdingTable,MetricDetailTable}.vue` |
| 共用 composable | `frontend/src/composables/temperature/useTemperatureOverview.ts` |
| 路由与免登录 | `frontend/src/router/modules/remaining.ts:44-65`、`frontend/src/router/index.ts:123` |
| 导航配置 | `frontend/src/components/MarketHeader/config.ts` |
| 行业拥挤度实现 | `backend/app/services/thermometer/industry_crowding.py:165,243,528,543,565` |
| 调度入口 | `backend/app/tools/scheduler.py`、`backend/app/services/sync/orchestrator.py:158` |
| CI 调度失败 | `gh run list --workflow=daily-snapshot.yml` + run 34519744964 `--log-failed` |
| 本地库数据 | 只读打开 `backend/invest.db` 查 `market_single_values` / `market_composites` / `market_multi_items` |
| 部署配置 | `vercel.json`、根 `package.json`、`scripts/build-landing.mjs`、`frontend/public/logos/` |
| 历史设计意图 | `docs/spec/site-architecture-and-traffic-routing.md`、`docs/spec/launch-priority-baseline.md`、`docs/working-notes/explore-watchlist-replan-2026-08-08.md`（#893） |

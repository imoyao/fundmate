# 基金投顾「基本信息 + 持仓比例」数据接口调研

> 调研时间：2026-07-22 ｜ 范围：天天基金（东方财富）、且慢（盈米）、蛋卷基金（雪球）三平台
> 目标：获取**基金投顾策略/组合的基本信息**与**持仓比例**（组合内各基金占比 / 单只基金重仓股债占比）
> 方法：GitHub + 公开文档检索 + 对公开接口做实测请求（非登录态）

> ⚠️ **勘误（2026-07-22 续）**：本文早期版本判定"天天基金投顾组合持仓需登录/无稳定公开端点"。经后续逆向与实测，该结论**已推翻**——天天基金投顾数据真实后端 `uni-fundts.1234567.com.cn` + `dataapi.1234567.com.cn` **免登录、免签名**即可返回结构化持仓/概览。文中相关结论表、平台对比与 §3.3、§6 矩阵均已同步修正；权威细节见《投顾持仓接口_技术方案与待决问题.md》。

---

## 一、结论速览（TL;DR）

| 维度 | 结论 |
|------|------|
| **投顾组合基本信息**（名称/管理人/成立日/风险/收益） | 三平台均可获取；**且慢最规范**（官方 MCP），蛋卷次之（公开 JSON），**天天基金已打通公开组合接口**（uni-fundts + dataapi，免登录） |
| **投顾组合持仓比例**（策略内各基金占比） | **且慢 MCP（`BatchGetStrategiesComposition`）与天天基金公开 API 并列可用**；蛋卷仍需登录态 |
| **单只基金持仓比例**（重仓股/债占比） | 天天基金/东方财富接口**最稳定**（已实测可用），且慢 MCP、AKShare、efinance 均可 |
| **你的最优路径** | **且慢 MCP + 天天基金公开 API 双源并行**（你已持有且慢 Key，天天基金免登录免 Key）；东方财富 `fundf10` 作单只基金穿透源，蛋卷作基本信息补充 |

> 关键判断：投顾组合持仓并非只能走“登录态/官方授权”。**天天基金实测已打通免登录公开接口**（见《投顾持仓接口_技术方案与待决问题.md》第 1、3 节）：`uni-fundts.1234567.com.cn` 提供业绩/行业/调仓明细，`dataapi.1234567.com.cn` 提供字段最全的概览；且慢官方 MCP 同样稳定。二者并列作为主源即可，无需依赖网页抓取或登录态。

---

## 二、三平台接口能力对比

| 平台 | 基本信息接口 | 投顾组合持仓比例 | 单只基金持仓 | 鉴权方式 | 稳定性/可用性 |
|------|------------|----------------|------------|---------|-------------|
| **且慢（盈米）** | MCP `GetStrategyDetails` | ✅ MCP `BatchGetStrategiesComposition` | ✅ MCP `BatchGetFundsHolding` | **API Key（MCP）** | ★★★★★ 官方、结构化、稳定 |
| **蛋卷（雪球）** | `GET /djapi/plan/{code}`（实测可用） | ⚠️ 需登录态（2026 实测：未登录仅返回精简字段） | pysnowball / App 接口 | Cookie / 登录态 | ★★★ 公开基本信息可用，持仓收紧 |
| **天天基金（东方财富）** | ✅ 公开 API `FundIATGInfoAggr`（dataapi，最全） + `getTGQuoteByFavor` | ✅ 公开 API `getAdjustWarehouse(tag=0/1)`（uni-fundts，免登录实测可用） | ✅ `fundf10.eastmoney.com` `type=jjcc`（实测可用） | 免登录/免签名（uni-fundts + dataapi） | ★★★★★ 组合与单只持仓均公开可达 |

---

## 三、各平台详解

### 3.1 且慢（盈米）—— 推荐主源 ✅

且慢提供**官方 MCP 服务（盈米且慢 MCP）**，共 **72 个金融工具**，分五大模块。与你的需求直接对应的工具如下：

**① 投顾策略基本信息 / 持仓（核心需求）**

| 工具名 | 功能 | 对应你的需求 |
|--------|------|------------|
| `GetStrategyDetails` | 获取且慢投顾策略详情（名称、管理人、风险、业绩基准等） | 投顾**基本信息** |
| `BatchGetStrategiesComposition` | **批量获取投顾策略最新持仓基金**（含各基金占比） | 投顾组合**持仓比例** ✅ |
| `BatchGetPoTradeComposition` | 获取策略当前可买入的交易成分基金 | 组合成分 |
| `GetStrategyAssetClassAnalysis` | 策略穿透后大类资产分布（股/债/货基占比） | 资产配置比例 |
| `GetStrategyBenchmark` / `GetStrategyRiskInfo` | 业绩基准 / 风险信息 | 基本信息补充 |
| `GetPortfolioNavHistory` | 策略历史净值走势 | 净值序列 |

**② 单只基金持仓 / 穿透（用于组合穿透分析）**

| 工具名 | 功能 |
|--------|------|
| `BatchGetFundsHolding` | 批量获取基金十大重仓股/债及占比 |
| `GetFundAssetClassAnalysis` | 基金大类资产分布（穿透底层） |
| `GetFundIndustryAllocation` | 基金各行业配置比例 |
| `GetFundIndustryConcentration` | 基金行业集中度（前5大行业占比） |

**调用方式**（与你已有的 Key 对应）：

```bash
# 环境变量注入你持有的且慢 MCP Key
export QIEMAN_API_KEY="zQAX3vgba6IxfhXQOxu_RQ"

# 查询某投顾策略的持仓基金及比例
mcporter call qieman-mcp.BatchGetStrategiesComposition \
  --args '{"strategyCodes":["ZH000193"]}' --output json

# 查询单只基金重仓
mcporter call qieman-mcp.BatchGetFundsHolding \
  --args '{"fundCodes":["005827"]}' --output json
```

> 单次批量上限 **10 只**；完整工具清单见 `https://qieman.com/mcp/tools`（已整理于本报告附录）。

**旧版网页爬虫接口（备用，需 x-sign）**：`https://qieman.com/pmdj/v1/pomodels/{poCode}`
- 返回 JSON 含 `composition` 数组，每个元素为 `fundCode / fundName / percent`（持仓比例），如 `519736 交银新成长混合 | 0.1343`。
- 鉴权：请求头 `x-sign`（13位时间戳+32位加密串，**每日失效**，需用 Selenium 模拟浏览器捕获）。**稳定性差，仅作兜底，不建议生产依赖。**

### 3.2 蛋卷基金（雪球）

**基本信息接口（实测 2026-07-22 可用）**

```
GET https://danjuanapp.com/djapi/plan/{plan_code}     # 例：CSI1033
GET https://danjuanfunds.com/djapi/plan/{plan_code}   # 同上，双域名均 200
```

实测返回字段（**已精简，无持仓比例**）：
`plan_code, plan_name, type, found_date, invest_time_type, invest_money_type, found_days, follower_count, status_count`

⚠️ 注意：2021 年公开博客中的完整结构（含 `plan_derived.unit_nav`、`yield`、收益率曲线等）及 `/rebalancing`、`/position` 子路径，**当前已失效**（实测返回“服务器错误”）。组合详情页为纯前端 SPA（HTML 仅 3.7KB，无内嵌数据），持仓比例需在**登录态/App**下获取——这是合规收紧的结果。

**补充：Python 库 `pysnowball`** 封装了蛋卷（雪球）基金数据接口（`fund_info`、`fund_nav_history` 等），适合拿基金基础信息与净值；组合持仓仍需登录态。

### 3.3 天天基金 / 东方财富

**单只基金持仓（实测 2026-07-22 可用）**

```
GET https://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={6位基金代码}&topline=10
# 例：code=005827 → 返回易方达蓝筹精选混合前十大重仓股及占比（HTML 格式，HTTP 200）
```

**投顾组合（⚠️ 勘误：已打通免登录公开接口，2026-07-22 实测）**：组合持仓比例**无需前端抓取或登录态**，经逆向 App bundle 已定位真实后端：

```
# 业绩/净值 + 行业配置 + 当前/历史基金级持仓（uni-fundts，POST，免登录/免签名）
POST https://uni-fundts.1234567.com.cn/combine/investAdviserInfo/getTGQuoteByFavor
POST https://uni-fundts.1234567.com.cn/combine/investAdviserInfo/getHoldWarehouseIndustryRatio
POST https://uni-fundts.1234567.com.cn/combine/investAdviserInfo/getAdjustWarehouse   # tag=0 当前持仓, tag=1 历史调仓
# 投顾概览（dataapi，GET，字段最全：TGNAME/RISKLEVEL/SYL_*/STGCONCEPT...）
GET  https://dataapi.1234567.com.cn/dataapi/IAAGGR/FundIATGInfoAggr?FIELDS=...&TGCODE={tgCode}
```

输入为分享链接里的 `tgCode`（如越海 `XCOVSEX`）。脚本见 `fund_advisor_holdings.py`，三步可跑通（`--healthcheck` 全绿）。详细的接口契约、参数示例与踩坑见《投顾持仓接口_技术方案与待决问题.md》。

> 实测 `type=zcpz`（资产配置）对部分基金返回空，建议以 `jjcc`（重仓股）为主做单只基金穿透。

---

## 四、GitHub 开源项目清单

| 项目 | 地址 | 用途 | 是否含投顾组合持仓 | 关键技术 |
|------|------|------|------------------|---------|
| **fund-advisor** | github.com/realqiyan/fund-advisor | 个人基金持仓统一管理 + 分析 | ✅ 经**且慢 MCP** 获取策略/基金持仓 | Python + mcporter + SQLite |
| **daleluopan（大乐罗盘）** | github.com/daleshi/daleluopan | 聚合蛋卷/东财/天天基金/知有行，指数估值+基金净值 | ❌ 偏估值与净值，非组合持仓 | Node.js + Express |
| **TiantianFundApi** | github.com/kouchao/TiantianFundApi | 天天基金 Node.js API 服务 | ⚠️ 基金数据，组合持仓需扩展 | Node.js |
| **FundCrawler**（SivanLaai） | github.com/SivanLaai/FundCrawler | 天天基金全量基金信息/净值/成分/经理 | ⚠️ 单只基金层 | Python 爬虫 |
| **FundCrawler**（Jerry1014） | github.com/Jerry1014/FundCrawler | 基金类型/规模/净值/经理/风险指标 | ⚠️ 单只基金层 | Python 爬虫 |
| **fund-holdings** | github.com/Lson-L/fund-holdings | 获取基金最新重仓股及比例 | ⚠️ 单只基金重仓 | Python |
| **akshare** | github.com/akfamily/akshare | 综合金融数据接口库 | ⚠️ 含蛋卷 `fund_individual_detail_info_xq` | Python |

**重点推荐 `realqiyan/fund-advisor`**：它本质是把“基金E账户导出的全平台持仓 CSV”导入本地 SQLite，再**调用且慢 MCP（`qieman-mcp.BatchGetFundsDetail` / `BatchGetFundsHolding`）做数据增强**——正好验证了“且慢 MCP 是投顾/基金持仓最可靠源”的判断，且与你已有的 API Key 可直接复用。

---

## 五、第三方 Python 库对照

| 库 | 覆盖平台 | 投顾组合持仓 | 单只基金持仓 | 备注 |
|----|---------|------------|------------|------|
| **akshare** | 蛋卷/东财/天天等 | ⚠️ 有限 | ✅ | `fund_individual_detail_info_xq` 取蛋卷数据 |
| **efinance** | 东方财富系 | ⚠️ | ✅ | 天天基金净值/持仓稳定 |
| **pysnowball** | 雪球/蛋卷 | ❌ | ✅ | 基金基础信息+净值 |
| **TiantianFundApi** | 天天基金 | ⚠️ | ✅ | 需自行部署 Node 服务 |

---

## 六、持仓比例获取可行性矩阵

| 数据类型 | 且慢 | 蛋卷 | 天天基金/东财 | 推荐源 |
|---------|------|------|-------------|--------|
| **投顾策略基本信息** | ✅ MCP | ✅ 公开 JSON | ✅ 公开 API `FundIATGInfoAggr` | 且慢 MCP 或 天天基金公开 API |
| **投顾组合持仓比例**（策略内各基金占比） | ✅ `BatchGetStrategiesComposition` | ❌ 需登录 | ✅ 公开 API `getAdjustWarehouse` | **且慢 MCP 与天天基金公开 API 并列** |
| **单只基金重仓股/债比例** | ✅ MCP | ✅ pysnowball | ✅ `fundf10 jjcc` | 东方财富（最稳）或且慢 MCP |
| **大类资产配置比例** | ✅ `GetStrategyAssetClassAnalysis` | ❌ | ⚠️ | 且慢 MCP |

---

## 七、结合你项目的推荐实施方案

你的资源：**满福/慢富**品牌 + **市场温度计**工具 + **且慢 MCP API Key**（已持有）。

**方案：以且慢 MCP 为投顾数据主源，东方财富作穿透补充**

1. **主源（投顾组合）**：用且慢 MCP 拉取目标策略的 `GetStrategyDetails`（基本信息）+ `BatchGetStrategiesComposition`（持仓比例）+ `GetStrategyAssetClassAnalysis`（大类资产）。结构化 JSON、稳定、可商用。
2. **穿透源（单只基金）**：对组合内的基金代码，用东方财富 `fundf10?type=jjcc` 或且慢 MCP `BatchGetFundsHolding` 取重仓股债比例，做“组合→基金→个股”穿透。
3. **补充源（基本信息）**：蛋卷 `djapi/plan/{code}` 取公开基本信息（名称/关注数/类型），用于横向对比多平台同策略。
4. **市场温度计整合**：投顾组合的整体股债配比、行业集中度，可直接作为“温度计”的资产配置维度输入；且慢 MCP 还自带 `GetLatestQuotations`（市场温度计与行情解读）工具。
5. **工程化建议**：用 `mcporter` 封装且慢 MCP 调用（参考 fund-advisor 项目），本地 SQLite/JSON 缓存，设置每日定时刷新（持仓比例类数据按日更新即可）。

**合规提醒**：
- 投顾组合持仓属于需适当性管理的信息，**不要公开分发原始持仓明细**；对内分析/自家产品展示需评估授权范围。
- 且慢 MCP 的调用受 API Key 配额与条款约束，生产前确认 QPS/商用授权。
- 蛋卷的网页抓取存在反爬与条款风险，仅建议作为非商用的个人分析补充；**天天基金投顾组合持仓走的是免登录公开 API（`uni-fundts` + `dataapi`），不涉及网页抓取**，可放心用于每日自动化。

---

## 八、实测记录（2026-07-22）

| 实测项 | 结果 |
|--------|------|
| 蛋卷 `GET /djapi/plan/CSI1033`（danjuanapp.com & danjuanfunds.com） | HTTP 200，返回精简基本信息（**无持仓比例字段**） |
| 蛋卷 `/djapi/plan/CSI1033/rebalancing`、`/position` | HTTP 200 但返回“服务器错误”（子路径已失效） |
| 蛋卷策略详情页 `https://danjuanapp.com/strategy/CSI1033` | 纯前端 SPA，HTML 3.7KB，无内嵌数据（需渲染/登录） |
| 东方财富 `fundf10?type=jjcc&code=005827` | HTTP 200，返回易方达蓝筹精选混合前十大重仓股及占比 |
| 东方财富 `type=zcpz`（资产配置） | 部分基金返回空，不建议依赖 |
| 且慢 MCP 工具清单 | 72 工具，持仓类齐全（见附录） |

---

## 附录：且慢 MCP 持仓/详情相关工具清单（节选）

**金融数据模块（持仓/详情/净值）**
- `BatchGetFundsDetail` / `BatchGetFundNavHistory` / `BatchGetFundTradeRules` / `BatchGetFundTradeLimit`
- `BatchGetFundsHolding`（单只基金十大重仓股/债）
- `GetFundAssetClassAnalysis` / `GetFundIndustryAllocation` / `GetFundIndustryConcentration`
- `GetStrategyDetails` / `BatchGetStrategiesComposition`（**投顾组合持仓**）/ `BatchGetPoTradeComposition`
- `GetStrategyAssetClassAnalysis` / `GetPortfolioNavHistory` / `GetStrategyBenchmark` / `GetStrategyRiskInfo`
- `GetAssetAllocation` / `DiagnoseFundPortfolio` / `GetFundsCorrelation`

**投顾服务模块**
- `GetAssetAllocationPlan` / `GetCompositeModel` / `AnalyzeInvestmentPerformance` / `StrategySearchByKeyword`
- `GetLatestQuotations`（市场温度计与行情解读）

> 完整 72 工具见官方文档：`https://qieman.com/mcp/tools`，或 `fund-advisor` 仓库 `references/mcp-tools-full.md`。

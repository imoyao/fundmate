# 外部数据源参考手册（2026-08-03）

> 性质：内部备忘（`docs/working-notes/` 屏蔽出构建，不对外）。
> 编制日期：2026-08-03
> 范围：多倍贝项目当前代码里所有外部数据源（行情 / 基金 / 市场温度 / 估值 / 认证）
> 依据：实际读取 `backend/app/services/thermometer/{constants,fetchers}.py`、`backend/app/services/sync/adapters/{akshare,xalpha}_adapter.py`、`backend/app/services/bias/calculator.py`、`pyproject.toml`，以及本会话对腾讯 / 东财 push2his 的实跑验证。
> 借鉴视角：参考 `daily_stock_analysis` 的 `data_provider`（15+ 抓取器 + 故障切换 + 熔断，LLM 仅写报告、不进数据链路）。
> **文档关系（本系列三件套，避免重复维护）**：本文＝**端点清单 SSOT**（host/端点/参数/Token/实时状态/适用性，只在此处维护）；[bias-datasource-replacement-2026-08-03](./bias-datasource-replacement-2026-08-03.md)＝具体改造记录（借本文端点绕过 akshare 腐烂，含专属代码）；[datasource-priority-plan-2026-08-03](./datasource-priority-plan-2026-08-03.md)＝通用排查树 + 优先级/熔断机制（端点与实跑证据引用本文）。

---

## 本系列文档索引（开发必读）

| 文档 | 角色 | 何时看 |
|---|---|---|
| [external-datasource-reference-2026-08-03](./external-datasource-reference-2026-08-03.md) | **端点清单 SSOT**（host / 端点 / 参数 / Token / 状态 / 适用性） | 要接 / 排查任何一个外部源时 |
| [bias-datasource-replacement-2026-08-03](./bias-datasource-replacement-2026-08-03.md) | 乖离度绕过 akshare 的具体改造 + 代码 | 接 `PriceFetcher` / 看 bias 怎么解时 |
| [datasource-priority-plan-2026-08-03](./datasource-priority-plan-2026-08-03.md) | 排查树 + 优先级分层 + 熔断 / 缓存机制 | 任何源异常、要设计 failover 时 |
| `通用数据源优先级路由.py`（沙箱 `/workspace/`，未入库） | 上述机制的参考实现（待开发接入验证） | 要落地 router 时 |
| [fundfof-borrowing-analysis-2026-08-03](./fundfof-borrowing-analysis-2026-08-03.md) | 功能借鉴（mock 页 / 回撤 / Sharpe / 对比页） | 排产品功能优先级时 |
| [landing-login-sso-2026-08-04](./landing-login-sso-2026-08-04.md) | 落地页 / SSO 决策 | 做登录 / 跳转 / 登录态时 |

> 端点与实时状态只在本文件维护；其余文档交叉引用，改一处不会漏三处。

## 一、总览表

| # | 数据源 | 用在哪 | 取什么 | Token | 本会话状态 | 适用 verdict |
|---|---|---|---|---|---|---|
| 1 | 新浪行情（经 akshare） | `akshare_adapter.fetch_stock_price` | A 股股票日线(qfq) | 免 | 代码在用；上游=新浪公开 | ✅ 适用（依赖 akshare 包装） |
| 2 | 东财 push2.eastmoney.com | `EastmoneyVolumeFetcher` | 全市场成交额(沪/深/北) | 免(带 Referer) | 代码在用，注释"已验证可用" | ✅ 适用 |
| 3 | 东财 push2his.eastmoney.com | 乖离度修复 `fetch_close_eastmoney` | 指数 K 线(含申万 90.x) | 免(**必须带 Referer**) | **本会话实跑通过** | ✅ 适用（新验证） |
| 4 | 腾讯 web.ifzq.gtimg.cn | 乖离度修复 `fetch_close_tencent` | 股票/ETF/宽基日 K | 免 | **本会话实跑通过** | ✅ 适用（新验证） |
| 5 | xalpha（gitee fork） | `xalpha_adapter` + `DailyWorth` | 基金净值 / 费率 / 货币基金 | 免 | 代码在用 | ✅ 适用（基金主源） |
| 6 | akshare 基金元数据 | `akshare_adapter` | 基金列表/详情/经理 | 免 | 代码在用 | ⚠️ 适用但有 akshare 断更风险 |
| 7 | 集思录 jisilu.cn | `JisiluCBFetcher` / `JisiluIndicatorFetcher` | 可转债温度 + 估值指标(PB/PE温度) | **需登录 Cookie** (`JISILU_COOKIE`) | 代码在用 | ✅ 适用（需 Cookie） |
| 8 | 且慢 MCP stargate.yingmi.com | `QiemanFetcher` | 市场温度计(中证全A) | **需 `QIEMAN_API_KEY`** | 代码在用 | ✅ 适用（需 key） |
| 9 | 有知有行 youzhiyouxing.cn | `YouzhiyouxingFetcher` | 全市场温度(SSR 解析) | 免 | 代码在用 | ✅ 适用 |
| 10 | 韭圈儿 jiucaishuo.com | `JiucaishuoFetcher` | 恐贪指数 + 中长期温度 | 免(API+Playwright) | 代码在用 | ✅ 适用（含浏览器降级） |
| 11 | akshare 宏观/估值 | `SelfCalcFetcher` | 沪深300 PE / 10Y 国债 / CPI | 免 | 代码在用(走缓存) | ⚠️ 适用但有 akshare 风险 |
| 12 | Supabase Auth | 全站登录 | 用户认证 / user 表 | 项目自带 | 已接入 | ✅ 适用（基础设施） |
| 13 | Playwright | 韭圈儿降级渲染 | 无头浏览器取数 | 免(本地工具) | 已装(pyproject) | ✅ 适用（降级手段） |

> 富来智投(api.fulaizhitou.com)、行业拥挤度(industry_crowding, Tushare>baostock>legulegu) 在代码里为**可选/已移除**源，未接入聚合流程，本文不纳入主表。

---

## 二、各源详情（端点 / 接入方式 / 注意点）

### A. 行情与价格

**① 新浪行情（经 akshare `stock_zh_a_daily`）**

- 调用：`ak.stock_zh_a_daily(symbol=to_sina_code(symbol), start, end, adjust='qfq')`
- 覆盖：A 股股票日线（开高低收/量/复权）。
- 注意：走 akshare 包装；上游是新浪公开接口。若 akshare 该函数崩，可直连新浪（与乖离度修复同理）。

**② 东财成交额 `push2.eastmoney.com`**

- 端点：`https://{push2|push2delay}.eastmoney.com/api/qt/stock/get?secid={1.000001}&fields=f48`
- secid 映射：上证 `1.000001` / 深证 `0.399001` / 北证 `0.899050`。
- 必须 `headers={'Referer':'https://quote.eastmoney.com/'}；双 host 轮询 + 3 次重试。
- 取 `data.f48`（成交额，元）→ /1e8 得亿。

**③ 东财指数 K 线 `push2his.eastmoney.com`（乖离度修复，本会话新验证）**

- 端点：`https://push2his.eastmoney.com/api/qt/stock/kline/get`
- 参数：`secid`(1.x 沪宽基 / 0.x 深宽基 / 90.x 申万行业)、`fields1=f1,f2,f3`、`fields2=f51,f53`、`klt=101`(日)、`fqt=1`(qfq)、`beg=0&end=20500101`
- **关键：不带 Referer 会被服务端直接断连接（`RemoteDisconnected`）**；带 `Referer: https://quote.eastmoney.com/` 后稳定。
- 本会话实测：沪深300(1.000300)=5242行、上证(1.000001)=8696行、创业板(0.399006)=3928行、申万农林(90.801010)=1180行，均成功。偶发连接中断，建议 2s 退避重试（≤4 次）。

**④ 腾讯日 K `web.ifzq.gtimg.cn`（乖离度修复，本会话新验证）**

- 端点：`https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sh/sz/bj}{code},day,{start},{end},800,qfq`
- 免 token、免 Referer、极稳。
- 本会话实测：沪深300/上证/茅台/300ETF/创业板指 全部 OK（81–82 行）；**申万行业 `sh801010` 返回 0 行（腾讯不覆盖）**——申万必须走东财 ③。

### B. 基金

**⑤ xalpha（gitee fork `imoyao/xalpha@master`）**

- 用途：基金净值（`xa.fundinfo(code).price` / `xa.mfundinfo` 货基）、费率（`fund.rate` / `fund.feeinfo`）。
- 覆盖：场外开放式基金 + 货币基金；**不支持股票/列表/经理**。
- 定位：多倍贝基金净值主源（`DailyWorth` 同步即走它）。乖离度对场外基金应复用此净值，而非 AKShare。

**⑥ akshare 基金元数据**

- 列表：`ak.fund_name_em()`；详情：`ak.fund_info_ths(symbol)`（类型/公司/成立日/基准/费率/经理）；经理：`ak.fund_manager_em()`（全量一次后筛选）。
- `fetch_fund_nav` 在 akshare_adapter 里 `raise NotImplementedError`——净值只走 xalpha。
- 风险：全靠 akshare；某函数断更会拖垮基金元数据同步。

### C. 市场温度 / 情绪

**⑦ 集思录 jisilu.cn**

- 可转债温度：`https://www.jisilu.cn/data/indicator/get_cb_temperature/`（取 `cb_temperature`）。
- 估值指标：`https://www.jisilu.cn/data/indicator/get_last_indicator/`（median_pb/pe 温度、stock_count 等）。
- 需 `headers={'Referer':'https://www.jisilu.cn/data/indicator/'}`；温度值需登录态 Cookie（`JISILU_COOKIE`=kbzw__Session），注释称"配即用官方真值"。

**⑧ 且慢 MCP（Streamable HTTP）**

- 端点：`https://stargate.yingmi.com/mcp/v2`，`protocolVersion=2024-11-05`，工具 `GetLatestQuotations`。
- 鉴权：`x-api-key: <QIEMAN_API_KEY>`（环境变量），并维护 `Mcp-Session-Id`。
- 支持 SSE 与 JSON 两种返回；取 `temperatureList` 里 `temperatureIndexCode=='000985'`(中证全A) 的温度。
- 未配 key 则优雅跳过。

**⑨ 有知有行**

- 端点：`https://youzhiyouxing.cn/thermometer`（SSR 网页）。
- 解析：`tw-text-[40px]` 后的 `(\d+)°` 取温度，匹配 `tw-leading-normal` 得标签；并抓沪深300/中证500/上证50 分指数温度。
- 免 token。

**⑩ 韭圈儿**

- 主路 API：`POST https://apiv2.jiucaishuo.com/site/indexes`（空 body + `Referer: https://app.jiucaishuo.com/`），返回 `data.data[]`，匹配"短期情绪"/"中长期温度"。
- 降级：API 失败时 Playwright 无头渲染 `https://app.jiucaishuo.com/`，读正文"短期情绪 N 标签 / 中长期温度 N℃ 标签"。
- 两阶段保证稳定性；免 token。

### D. 自算估值

**⑪ akshare 宏观/估值（股债利差）**

- `ak.stock_index_pe_lg('沪深300')` → PE；`ak.bond_zh_us_rate()` → 10Y 国债；`ak.macro_china_cpi()` → CPI 同比。
- 本地算 EY=1/PE，spread=EY−y10/100+0.3·CPI/100，取今日利差历史分位。
- CPI 接口最慢（约 19 页），走 12h 文件缓存（`_cached`）。全依赖 akshare。

### E. 认证 / 工具

**⑫ Supabase Auth**：登录/注册/user 表，项目自带，落地页仅做跳转、不做 SSO（见 [landing-login-sso-2026-08-04](./landing-login-sso-2026-08-04.md)）。

**⑬ Playwright**：`sync_playwright()` 无头 Chromium，用于韭圈儿降级；`pyproject` 声明 `playwright>=1.61.0`。

---

## 三、适用性结论（给多倍贝）

1. **行情三件套已闭环**：股票/ETF/宽基用腾讯直连（稳），申万用东财 push2his+Referer（本会话验证），基金净值用 xalpha——乖离度阻塞点已解（详见 [bias-datasource-replacement-2026-08-03](./bias-datasource-replacement-2026-08-03.md)）。
2. **市场温度矩阵完整且分层**：稳定层（东财成交额/韭圈儿/集思录）＋ 脆弱层（且慢/有知有行）＋ 自算层（股债利差），单源失败不影响整体。
3. **AKShare 是全局脆弱点**：行情日线、基金元数据、自算估值的若干函数都经 akshare 包装。乖离度已因 akshare 断更被迫直连上游；**同理建议**：对行情日线、基金元数据、宏观估值的关键函数，逐个评估"直连上游/加重试/加熔断"的必要性，避免重蹈乖离度覆辙。
4. **需授权/Cookie 的源**：集思录(登录Cookie)、且慢(API key) 属"配置即有、缺失即跳过"，不影响主链路——保持现状即可。

---

## 四、借鉴 daily_stock_analysis 的工程经验

- 它 15+ 抓取器（akshare/yfinance/tushare/longbridge/tencent/efinance/pytdx/baostock/finnhub/alphavantage/tickflow…）本质是**对同一批上游（东财/腾讯/新浪/雅虎…）的多实现**，用**策略模式 + 优先级有序链 + 异常降级 + 熔断**兜底。
- **数据链路零 AI**：LLM(LiteLLM/Gemini) 只在 `analyzer.py` 生成报告/评分/决策，且代码可 `stabilize_decision_with_structure` 覆盖模型——所以它的数据不"依赖 AI"。
- 对多倍贝的启示：把"取数"与"分析/生成"解耦；关键取数做多源 + 重试 + 熔断，正是乖离度修复已落地的方向。

---

## 五、边界

- **事实**：以上端点/host/参数均来自本会话实际读取的源码与 `constants.py`；腾讯、东财 push2his 两项为本会话 `requests` 实跑通过（附行数与末值）。
- **推断**：AKShare 崩的函数其上游（新浪/东财/腾讯）通常仍可用，故直连可解；东财连接中断为限速/反爬，Referer+退避可破。
- **未知**：海外免费部署机的出网是否被墙（需代理）；各公开端点长期稳定性；集思录 Cookie、且慢 key 的获取与续期方式；基金元数据 akshare 函数何时可能断更。

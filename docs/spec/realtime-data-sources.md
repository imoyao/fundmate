---
title: 自选实时数据接口源归集（realtime-data-sources）
---

# 自选实时数据接口源归集（realtime-data-sources）

本文档是**前端外部数据源的权威归集**，覆盖自选股池（watchlist）获取实时股价、场外基金估值所使用的外部接口，以及新增字段时必须遵守的约束。

> 定位：与 `api.md`（后端自有 API 端点）不同，本文档只记录**前端直连的外部数据源**（JSONP 注入，绕过同源策略）。后端 API 不在此列。

## 1. 当前已接入的外部数据源

| 数据源 | 用途 | 接入方式 | 字段/产物 | 状态 |
|---|---|---|---|---|
| `fundgz.1234567.com.cn`（天天基金估值接口） | 场外开放式基金盘中实时估值 | JSONP（`realtimeDataSources.ts` 注入 `<script>`） | 基金估算净值、估算涨跌幅 | 已用 |
| `qt.gtimg.cn`（腾讯财经行情） | A 股 / 股票实时行情 | JSONP | 股票现价、涨跌额、涨跌幅 | 已用 |

> 注：`qt.gtimg.cn` 返回 `v_xxxxxx="..."` 格式字符串，需解析；`fundgz` 返回 JSONP 回调包裹的估值对象。两个源前端侧统一经 `realtimeDataSources.ts` → `valuationEngine.ts` → `useRealtimeQuotes.ts` 链路消费。

### 1.1 待接入 / 备选数据源（来自 jigu 复盘，详见 `realtime-data-source-switching.md`）

| 数据源 | 用途 | 接入方式 | 状态 |
|---|---|---|---|
| 天天基金批量估值 `fundcomapi.tiantianfunds.com/mm/newCore/FundValuationLast`（`FCODES` 逗号拼 50 个一批） | 场外基金盘中估值**批量拉取** | JSONP / 批量 | 待评审（#990 主源候选） |
| 新浪基金估值 `stock.finance.sina.com.cn/fundInfo/api/.../getEstimateNetworthPic` | 天天接口降级/备选 | JSONP | 待评审（降级源候选） |
| 历史净值走势 `fundgz.1234567.com.cn/pingzhongdata/{code}.js`（`Data_netWorthTrend`） | Sparkline 统一历史源（替代本地累积缓存） | JSONP | 待评审（#990 Sparkline） |
| 腾讯行情多 code 批量 `qt.gtimg.cn/q=sh600519,sz000001` | 股票/指数一次拉全部 | JSONP | 待评审（#990 省请求） |

## 2. 新增字段 / 新接口的硬约束（来自 AGENTS.md）

1. **复用既有通道**：任何自选实时数据字段的新增，必须复用 `frontend/src/utils/realtimeDataSources.ts`，**不得**在前端各组件里另起 `<script>` 注入或硬编码接口地址。
2. **建立在 columnDefs 之上**：新字段的展示必须建立在 #995 的 `columnDefs` 数据驱动表格之上，**不得**往 `watchlist/index.vue` 的 21 个硬编码 `el-table-column` 上继续堆列。
3. **统一归集**：新发现的稳定接口源，必须先补进本文档第 1 节，再写代码；不在文档里的接口源视为未评审。
4. **跨域处理**：外部接口一律经 JSONP 直连，**禁止**引入需要后端代理却未落地代理方案的跨域调用；若必须走后端代理，须先开 issue 明确代理方案，不临时硬编码。

## 3. 相关 issue 归集（umbrella：#1016）

- #980 自选页面拆分重构（进行中，不能影响重构进程）
- #990 自选 Sparkline / 迷你走势（未做）
- #991 自选排序（已合并）
- #992 自选拖拽排序（未做）
- #993 自选表头自定义（未做）
- #995 columnDefs 数据驱动表格（前置，未做）

> 字段扩展需求（实时股价、场外基金估值之外的补充字段）统一挂 `scope:self-select-realtime` Label，不在本文档重复列清单，以 issue 为准。

## 4. 待评审 / 待补项

- 当前接口源的**稳定性与限流**：外部 JSONP 源无 SLA，生产环境是否需要后端代理兜底（见 AGENTS.md 跨域约束第 4 条）。
- 指数行情源（#962 债务项）与本文档数据源的整合，待 #995 落地后统一规划。
- **数据源切换与优选机制（来自 jigu 复盘）** 已单独立档 `realtime-data-source-switching.md`：含单基金 `dataSource`(1-4) 切换、自动优选 RPC（`get_best_valuation_source`）、双源降级链、以及 §3 可复用接口清单。fundmate 落地分两阶段：① 双源（天天批量主 + 新浪降级）+ 腾讯多 code + pingzhongdata 历史；② 后期建源准确率表实现自动优选。

---
title: 数据源切换与优选设计参考（来自 jigu 复盘）
---

# 数据源切换与优选设计参考（来自 jigu 复盘）

> 来源：复盘 `D:\codes\jigu`（叽咕 / 基估宝，Next.js）后萃取。
> 用途：为 fundmate 自选实时数据（#990/#995）预留「多数据源 + 自动优选 + 切换」能力。
> 状态：**参考文档，未实现**。落地前需开 issue 评审（AGENTS.md 约束第 4 条）。

## 0. 背景与目标

fundmate 当前 `realtimeDataSources.ts` 只有两个硬编码源（天天 `fundgz` 单只估值、腾讯 `qt.gtimg.cn` 行情），无切换/优选机制。
jigu 已有一套**按数据源 ID 分别取估值 + 自动选最佳源**的完整实现，可直接借鉴其设计，但**不复制其全部数据源**（部分依赖 jigu 自有 supabase 后端，fundmate 无此环境）。

本文档把 jigu 的「数据源枚举 / 切换 / 优选」机制拆清楚，并整理出 fundmate 可复用的**接口清单**，便于后期直接落地。

---

## 1. jigu 的数据源枚举（基金估值）

jigu 把基金估值源抽象为 4 个数字 ID，存于 `fund.dataSource`（单基金级别，可在 UI 切换）：

| ID | 名称 | 接口/源 | 是否 fundmate 可复用 | 备注 |
|----|------|---------|----------------------|------|
| 1 | 天天基金（默认） | `FundValuationLast`（移动端 `fundcomapi.tiantianfunds.com`）批量估值 | ✅ 可复用 | 见 §3.1，支持一次 50 个 FCODES 批量 |
| 2 | 新浪财经 | `FundInfoService.getEstimateNetworthPic`（`stock.finance.sina.com.cn/fundInfo/api/...`） | ✅ 可复用 | JSONP，仅给 `gszzl`（估算涨跌幅），无 `dwjz`/`jzrq`，需历史净值补全 |
| 3 | 新浪财经（备选） | 同上新浪接口 | ✅ 可复用（作为数据源 2 的等价冗余源） | jigu 内部作为备用通道 |
| 4 | supabase_qdii | jigu 自有 supabase 后端（QDII 海外净值代理） | ❌ 不可复用 | 依赖 jigu 后端，fundmate 无此环境；仅作「源类型示例」参考 |

> 自动模式（数据源 = 1 时的实际行为见 §2）：除 QDII 外，jigu 会额外探测「最佳源」再决定最终 `valuationSource`。

---

## 2. 切换机制：单基金 `dataSource` + 自动模式

### 2.1 入口 `fetchFundData(code, overrideDataSource)`

逻辑（`jigu/app/api/fund.js:1416`）：

1. 若 `overrideDataSource` 未传 → 从 localStorage `funds[]` 里读该基金的 `f.dataSource`（用户自选源），默认 `1`。
2. 历史净值 `lsjz` 用 `pingzhongdata` 走势（见 §3.3），与估值**并行**拉取（`lsjzPromise` + `gzPromise`）。
3. 估值：调 `fetchFundValuationBySource(code, dataSource)` → 见 §2.2。
4. **降级链**：估值失败 → `catch` 里调 `fetchFundDataFallback(code)`（最后兜底）。
5. **合并**：把 `lsjz` 的 `dwjz/jzrq/zzl`（最新单位净值/日期/涨跌）回填到估值结果；新浪源无 `dwjz` 时由 `lsjz` 补全。
6. `supabase_qdii` 或只有 `gszzl` 时，用 `gsz = dwjz * (1 + gszzl/100)` 反算估算净值。

### 2.2 `fetchFundValuationBySource(code, dataSource)` 分发

```
switch (dataSource) {
  case 2: return fetchSinaEstimateNetworthResponse(code)
  case 3: return fetchSinaEstimateNetworthResponse(code)   // 新浪备选
  case 4: return fetchSupabaseQdiiValuation(code)
  default (1): return fetchFundValuationBySourceAuto(code)  // 自动优选
}
```

### 2.3 自动优选 `fetchFundValuationBySourceAuto(code)`（`dataSource === 1`）

核心：`fetchFundBestSource(code)` 先发 RPC 探测「最佳源是哪类」，再分支：

```
bestSource = await fetchFundBestSource(code)   // 返回 'ttjj' | 'sinaEstimateNetworth' | 'supabase_qdii'
if (bestSource === 'supabase_qdii') return fetchSupabaseQdiiValuation(code)
if (bestSource === 'sinaEstimateNetworth') {
    const sina = await fetchSinaEstimateNetworthResponse(code)
    return sina || await fetchFundValuationLast(code)   // 新浪失败回退天天
}
// 默认天天
return fetchFundValuationLast(code)
```

#### RPC 探测：`fetchBestValuationSource(code)` / `fetchFundBestSource(code)`

- `fetchBestValuationSource`：调用 supabase RPC `get_best_valuation_source(fund_code)`，返回 `{ source, accuracy, ... }`。
- `fetchFundBestSource`：包装上者；**异常时 `catch` 返回默认 `'ttjj'`**（天天），保证自动模式永不崩。
- 说明：`get_best_valuation_source` 是 jigu 自有 supabase 函数，基于历史「各源准确率」统计选优。**fundmate 无此统计后端**，落地时有两个选择：
  - (A) 仅保留「天天主源 + 新浪降级」双源切换，暂不做「按准确率自动选」；
  - (B) 后期建 fundmate 自有「源准确率」记录表，再实现 RPC 优选（建议挂 #1016 umbrella 下单独 issue）。

---

## 3. 可复用接口清单（fundmate 落地用）

### 3.1 天天基金批量估值 `FundValuationLast` ★核心

```
GET https://fundcomapi.tiantianfunds.com/mm/newCore/FundValuationLast
    ?FCODES=110022,000001,161725   // 逗号拼多个，单次最多 50 个
    &FIELDS=FCODE,SHORTNAME,GSZZL,GZTIME,GSZ,NAV,PDATE
```

- 返回 `json.data[]`，每条：`FCODE / SHORTNAME / GSZ(估算净值) / GSZZL(估算涨跌幅%) / GZTIME(估值时间) / NAV(单位净值) / PDATE(净值日期)`。
- **前端用 DataLoader 模式合并并发请求**：同一微任务内所有基金单请求 → `setTimeout(0)` 聚合成 50 个一包的批量请求（`FUND_VALUATION_LAST_BATCH_SIZE=50`，staleTime=10s）。
- 字段映射（→ fundmate `Quote`）：`GSZ→currentPrice` / `GSZZL→changePct` / `SHORTNAME→name` / `GZTIME→time`。
- **这是 fundmate #990 想要「一次拉一批自选估值」的主源**，直接替换现有逐个 `fundgz.1234567.com.cn/js/{code}.js`。

### 3.2 新浪基金估值 `FundInfoService.getEstimateNetworthPic`

```
GET https://stock.finance.sina.com.cn/fundInfo/api/openapi.php/FdFundService.getEstimateNetworthPic
    ?symbol={code}&callback={jsonp_callback}
```

- JSONP 注入，10s 超时兜底（`resolve(null)`）。
- 仅返回 `gszzl`（估算涨跌幅），**无单位净值** → 需配合 §3.3 历史净值补全 `dwjz/jzrq`。
- 用途：作为天天接口的**降级/备选源**，提升鲁棒性。

### 3.3 历史净值走势（Sparkline 数据源，统一历史接口）★

```
GET https://fundgz.1234567.com.cn/pingzhongdata/{code}.js   // 东方财富底层
```

- 返回 JS 变量，关键数组：
  - `Data_netWorthTrend`：`[{ x: 时间戳(ms), y: 净值, equityReturn: 日涨跌% }, ...]` —— 全量净值序列。
  - `Data_grandTotal` / `Data_rateInSimilarType`：排名类指标（Sparkline 暂不需要）。
- **前端按 range（近 7/30/90 日）对 `x` 切片**，即得 Sparkline 点序列。
- 替代 fundmate「本地轮询累积缓存」方案：用户一个月没登也不会空图，跨设备一致。（对应 #990 Sparkline 需求）
- jigu 里 `fetchNavMetricsFromTrendFallback` / `fetchFundHistory` 均基于此。

### 3.4 腾讯行情多 code 批量（股票/指数实时）

```
GET https://qt.gtimg.cn/q=sh600519,sz000001,jj000001   // 逗号拼多个
```

- 一次请求返回全部：`v_sh600519=...;v_sz000001=...;v_jj000001=...`。
- fundmate 现状 `fetchTencentData` 每次只传一个 `fullCode`（未用多 code 能力）→ #990 改为传数组即可省请求。
- jigu `fetchMarketIndices`（`fund.js:1905`）即一次拉全部指数，证明该模式稳定。

### 3.5 基金持仓（次要，暂不需）

```
GET https://fundmobapi.eastmoney.com/FundMNewApi/FundMNInverstPosition
    ?FCODE={code}&deviceid=Wap&plat=WAP&product=EFund&version=2.0.0
```

- 移动端替代已失效的 `FundArchivesDatas.aspx`。fundmate 自选暂不需要，记录备查。

---

## 4. 切换/优选落地建议（fundmate）

按「先双源、后优选」两阶段：

### 阶段一（#990 可含）：双源切换 + 批量
- 主源：`FundValuationLast` 批量（§3.1），DataLoader 合并并发，staleTime 10s。
- 降级源：新浪估值（§3.2），天天失败时回退。
- 单基金 `dataSource` 字段（1=天天 / 2=新浪），存 localStorage / 后端自选配置。
- 股票/指数走腾讯多 code 批量（§3.4）。
- Sparkline 走 `pingzhongdata` 历史（§3.3），弃用本地累积缓存。

### 阶段二（#1016 umbrella 下单独 issue）：自动优选
- 建 fundmate 自有「源准确率」记录表（记录每次各源估值 vs 实际净值偏差）。
- 实现 `get_best_valuation_source` 等价 RPC，自动模式下按准确率选源。
- UI：`FundDataSourceSelector` 组件模式可借鉴（数据源徽章 + 切换下拉），但需适配 fundmate Vue 技术栈（jigu 为 React/JSX）。

---

## 5. 注意事项（踩坑记录）

1. **`F10DataApi.aspx`、`FundArchivesDatas.aspx` 已失效** → jigu 已迁移到 `pingzhongdata` / `FundMNInverstPosition`。fundmate 不要抄这两个老接口。
2. **新浪源无单位净值** → 必须与历史净值（§3.3）合并才能补全 `dwjz/jzrq`，否则排序/显示会缺数据。
3. **`fundcomapi.tiantianfunds.com` 是天天基金移动端新接口**，与旧 `fundgz.1234567.com.cn/js/{code}.js` 稳定性不同，建议主源 + 旧 `fundgz` 单只作最后兜底，而非直接删除旧源。
4. **JSONP 注入需清理**：jigu 用 `cleanupScript` 在 `onerror`/超时/`callback` 后 `removeChild` + `delete window[callback]`，防止内存泄漏与回调污染。fundmate `realtimeDataSources.ts` 现有 JSONP 封装已有类似处理，新增源须保持。
5. **并发合并用 DataLoader 而非裸 Promise.all**：50 个并发单请求若不合并，仍会发 50 次。必须用微任务 + `setTimeout(0)` 聚合（或直接用 `p-limit`/`dataloader` 库）。

---

## 6. 关联 issue（fundmate）

- #990 自选 Sparkline / 迷你走势（含批量估值源改造）
- #995 columnDefs 数据驱动表格（数据源切换 UI 的前置）
- #1016 umbrella：自选实时数据增强（自动优选、指数源整合等挂此下）
- #980 自选页面拆分重构（进行中，数据源改造不得阻塞）

> 本文档仅归集设计参考与接口清单，不承载代码。落地前按 AGENTS.md 第 4 条先评审、补 `realtime-data-sources.md` 第 1 节，再写代码。

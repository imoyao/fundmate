# 通用数据源优先级方案（防依赖腐烂）（2026-08-03）

> 性质：内部备忘（`docs/working-notes/` 屏蔽出构建，不对外）。
> 编制日期：2026-08-03
> 配套代码：`/workspace/多多贝_通用数据源优先级路由.py`（沙箱已实跑验证 failover / 熔断 / 缓存，未入库）
> 由来：乖离度因 akshare 一个函数腐烂而全功能阻塞 → 直连上游（腾讯 / 东财）复活。
> 目标：**下次任何数据源异常 / 端点不可用，按本方案机械执行即可，无需每次从零调研。**
> 文档关系：端点清单与实跑证据见 [external-datasource-reference-2026-08-03](./external-datasource-reference-2026-08-03.md)；乖离度改造实例见 [bias-datasource-replacement-2026-08-03](./bias-datasource-replacement-2026-08-03.md)。本文只定义「排查树 + 优先级分层 + 熔断 / 缓存机制」，端点不在本文维护。

---

## 一、核心理念（先记住这一条）

A 股数据的**真实上游只有几家**：东财 / 腾讯 / 新浪 / 天天基金 / 集思录。
`akshare`、`efinance`、`xalpha`、`yfinance`、`pytdx`、`baostock` 等都只是**这些上游的不同封装**。

- **换包 ≠ 冗余**：akshare 与 efinance 都包装东财，互为「假冗余」；真冗余必须换**上游**（东财→腾讯→新浪→天天基金）。
- 所以通用解法 = **按「能力（capability）」组织一组「不同上游」的 provider，按优先级故障切换 + 熔断 + 缓存**。这正是 `daily_stock_analysis/data_provider` 的做法，本方案复用其思想。

---

## 二、通用诊断树（数据源异常时，按序执行）

> 不需重新调研。照着走：定位 → 换封装 → 加 header → 换上游 → 全失败降级。

1. **定位：是我们的 bug 还是上游真挂？**
   用 `curl` / 裸 `requests` 直连该 provider 的**真实上游端点**（带最小必要 headers）。
   - 上游能返回 → 是我们这侧解析 / headers / 参数问题，修自己。
   - 上游也挂 / 限流 → 进入 2–4。

2. **若 wrapper 腐烂（akshare 某函数报错 / 返回空）**
   - 直连它包装的上游（端点见 external-datasource-reference），或换一个 wrapper（同上游用 efinance；不同上游用 pytdx / baostock / yfinance）。
   - 判据：见第五节「wrapper→上游映射」，确认换的是**不同上游**。

3. **若上游反爬（连接中断 / 403 / 空响应）**
   - 加 `Referer` / `User-Agent` / 必要 header（**东财必须带 `Referer: https://quote.eastmoney.com/`**，否则直接断连接）。
   - 退避重试（递增 sleep）。本会话验证：东财 push2his 缺 Referer 必败，加上 + 5×递增 3s 退避后稳定（但仍偶发限速）。

4. **若上游真限流 / 抖动**
   - 切到**不同上游**，开 TTL 缓存降频，开熔断防雪崩。`DataSourceRouter` 自动完成。

5. **全失败**
   - 返回 None / 用上次缓存值兜底 / 标 `stale`，**绝不静默或崩主链路**；把 `router.health()` 接入告警。

---

## 三、优先级分层（对多多贝的落地约定）

| 层 | 内容 | 角色 |
|---|---|---|
| **Tier 0 直连上游** | 腾讯 gtimg、东财 push2 / push2his（+Referer）、新浪 finance、天天基金 | **首选**，无 wrapper 脆弱性 |
| **Tier 1 轻量 wrapper** | efinance（东财）、xalpha（基金）、pytdx、baostock | 备选 / 补充 |
| **Tier 2 akshare** | 各类 `ak.*` 函数 | **仅最后兜底**，且每函数独立隔离（一个崩不影响其他） |
| **Tier 3 需授权** | Tushare / Longbridge / 且慢 key / 集思录 Cookie | 配置即有，缺失即跳过 |
| **自算层** | 股债利差等纯本地计算 | 零依赖，永不阻塞 |

> 注册顺序即优先级：Tier0 → Tier1 → Tier2 → Tier3。自算层作为「无数据也可用」的终兜。

---

## 四、能力 → Provider 矩阵（多多贝实际能力）

> 各源端点 / Token / 实时状态见 [external-datasource-reference-2026-08-03](./external-datasource-reference-2026-08-03.md)；本表为「能力 → provider」的**设计映射**。

| capability | Tier0 直连 | Tier1 wrapper | Tier2 akshare（兜底） | 备注 |
|---|---|---|---|---|
| `stock_daily` | 腾讯 gtimg / 新浪 finance | efinance / pytdx | `stock_zh_a_daily` | 腾讯本会话实测稳 |
| `etf_daily` | 腾讯 gtimg | efinance | `fund_etf_hist_em` | 腾讯实测稳 |
| `index_daily`（宽基） | 腾讯 gtimg / 东财 push2his | efinance | `index_zh_a_hist` | 腾讯稳；东财需 Referer |
| `sw_industry_daily`（申万） | **东财 push2his（secid 90.x）** | — | `index_zh_a_hist` | **腾讯不覆盖！必须东财** |
| `fund_nav` | 天天基金直连 | **xalpha** | `fund_open_fund_info_em`（已腐） | xalpha 主源 |
| `fund_meta` | — | — | `fund_name_em` / `fund_info_ths` / `fund_manager_em` | 依赖 akshare，关注断更 |
| `market_volume` | 东财 push2 | — | — | 已用 |
| `cb_temperature` | — | — | — | 集思录（需 Cookie）主 |
| `valuation_indicator` | — | — | — | 集思录（需 Cookie） |
| `market_thermometer` | — | — | — | 且慢 MCP（需 key）/ 有知有行 |
| `fear_greed` | — | — | — | 韭圈儿（API + Playwright） |
| `equity_bond_spread` | — | — | `stock_index_pe_lg` / `bond_zh_us_rate` / `macro_china_cpi` | 自算层，缓存 12h |

---

## 五、上游拓扑 & wrapper→上游映射（判断「是否真冗余」）

**真实上游（A 股）**：东财 / 腾讯 / 新浪 / 天天基金 / 集思录 / 交易所官方。
**需 token**：Tushare / Longbridge / 且慢 / 富来。
**海外**：Yahoo（yfinance）/ AlphaVantage / Finnhub。

| wrapper | 包装的上游 | 与谁「假冗余」 |
|---|---|---|
| akshare | 东财 / 腾讯 / 新浪 / 天天基金 / 韭圈儿…（最全，最易腐） | efinance（同东财）、xalpha 部分（同天天基金） |
| efinance | 东财 push2his | akshare 东财类 |
| xalpha | 天天基金 / 基金业协会 / 雪球 | akshare 基金类 |
| pytdx | 通达信（本地） | baostock（均为本地历史） |
| baostock | 自有（本地） | pytdx |
| yfinance | Yahoo | —（海外） |
| tushare | 自有（需 token） | Longbridge |

> **冗余判据**：两个 provider 的 `upstream` 字段不同，才算真冗余。路由模块里每个 `Fetcher` 都带 `upstream` 字段，便于审计。

---

## 六、机制规格（来自已验证的 `DataSourceRouter`）

- **故障切换**：`resolve(capability)` 按 priority 升序尝试，命中即返回；返回空 / 异常自动降级下一个。
- **熔断**：单 provider 连续失败 `threshold=3` 次 → `open`，`cooldown=60s` 后半开探测恢复。避免雪崩与无效重试。
- **重试**：退避在 provider 内部实现（东财 `5×递增3s`）；wrapper 层不重复重试。
- **TTL 缓存**：默认 3600s（行情可改为 1 天、温度几小时），降频 + 端点抖动时兜上次值。
- **健康监控**：`router.health()` 返回各 provider 熔断态，接监控 / 告警。
- **降级语义**：全失败抛 `RuntimeError(末因)`；调用方标 stale / 用缓存，不静默。

**实跑证据**：端点与逐源验证数据见 [external-datasource-reference-2026-08-03](./external-datasource-reference-2026-08-03.md) §一/§二 与 [bias-datasource-replacement-2026-08-03](./bias-datasource-replacement-2026-08-03.md) §三（腾讯稳、东财 push2his 需 Referer + 退避）。
本文 `DataSourceRouter` 自身已实跑验证：akshare 腐烂 → 自动降级腾讯取到真实收盘价 ✅；多源链降级到链尾 ✅；缓存命中不出网 ✅；连败 3 次熔断 `open` ✅。
**设计驱动发现**：东财 push2his 本沙箱 IP 偶发限速（缺 Referer 必败，加上仍偶发 `RemoteDisconnected`）——正说明缓存 + 熔断不是过度设计，而是必需。

---

## 七、落地步骤（把散装重试收口为统一路由）

1. 将 `多多贝_通用数据源优先级路由.py`（沙箱 `/workspace/`）拷到 `backend/app/services/common/data_source_router.py`。
2. `bias/calculator.py` 的 `PriceFetcher.fetch()`：按品种构造 capability，注册 腾讯（主）/ 东财（申万）/ akshare（兜底）provider，改调 `router.resolve()`（打通即解原阻塞）。
3. `thermometer/fetchers.py`：保留各 `Fetcher.fetch()` 实现，外层统一走 router 做 failover（替换现有散装 `_get` + 重试）。
4. 申万行业**当前只有东财一个真实上游**（腾讯不覆盖），建议补兜底：缓存上次成功值 +（可选）天天基金 / 雪球行业指数源，消除单点。
5. 把 `router.health()` 接入定时任务的告警输出。

---

## 八、边界

- **事实**：上游拓扑、wrapper 映射、能力矩阵均来自本会话实际读取的源码；router 的 failover / 熔断 / 缓存已实跑通过；东财从本沙箱偶发限速为实测。
- **推断**：A 股上游≈5 家，wrapper 即封装；换上游才是真冗余。
- **未知**：海外免费部署机出网是否受限；各端点长期稳定性；申万是否有第二个独立上游；集思录 Cookie / 且慢 key 的获取与续期方式。

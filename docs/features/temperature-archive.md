---
title: 市场温度工具 · 状态归档与待办梳理
---

# 市场温度工具 · 状态归档与待办梳理

> 归档日期：2026-08-03
> 作者：imoyao
> 定位：本文是「市场温度工具」的**唯一状态真相源**，取代此前散落在聊天记录里的两份长文档（技术文档与任务规划书 / 总文档）。
> 关联：`backend/app/services/thermometer/README.md`（后端实现说明）、`docs/features/temperature-redesign.md`（前端温度区设计稿）、`docs/overview-bias-stale-2026-08-02.md`（乖离率落库修复记录）。

---

## 〇、最重要的一句话提醒（先读）

你此前贴给我的两份长文档，描述的是**v1 独立工具形态**：

```plain
market_thermometer.py + bias.py + valuation_jiucai.py + industry_crowding.py
+ fund_concentration.py + store.py + notify_wechat.py + index.html（静态仪表盘）
```

这套代码**已不在本仓库**（搜不到 `market_thermometer.py` / `fund_concentration.py` / `store.py` / `index.html`）。当前仓库里，工具已被**重构为 v2 后端服务 + 前端视图**：

```plain
backend/app/services/thermometer/   (fetchers + service + jobs)
backend/app/services/bias/          (calculator + job + provider)
backend/app/domains/temperature/    (SQLAlchemy 三表模型)
frontend/src/views/temperature/     (Vue 温度视图) + explore 温度区
```

因此，整理时**不以贴文为真相，而以仓库真实代码为准**。贴文里标"✅已完成"的项，在本仓库里有三种真实状态：已接入 / 已写但禁用 / 根本未接入。下文逐条对齐。

---

## 一、已实现功能（按真实代码核对）

### 1.1 数据源 / 指标（已接入聚合流程）

| 指标 | 实现位置 | 真实状态 | 备注 |
|---|---|---|---|
| 全市场成交额（东财） | `SINGLE_FETCHERS['eastmoney_volume']` | ✅ 已接入 | 零凭据；偶发连不通时 `stale` 标灰 |
| 韭圈儿·恐贪 + 中长期温度 | `JiucaishuoFetcher` | ✅ 已接入 | **API 优先**：POST `apiv2.jiucaishuo.com/site/indexes`；失败降级 Playwright 渲染 |
| 集思录·可转债温度（官方） | `SINGLE_FETCHERS['jisilu_cb']` | ✅ 已接入 | 需 `JISILU_COOKIE`；失效降级近似 |
| 集思录·全市场估值（中位 PB/PE 温度） | `COMPOSITE_FETCHERS['jisilu_indicator']` | ✅ 已接入 | 需 cookie |
| 且慢·指数温度 | `SINGLE_FETCHERS['qieman']` | ✅ 已接入 | 官方 MCP `GetLatestQuotations` |
| 有知有行·全市场/债市温度 | `SINGLE_FETCHERS['youzhiyouxing']` | ✅ 已接入 | SSR `/data` 解析 |
| 自算·股债利差分位 | `COMPOSITE_FETCHERS['self_calc']` | ✅ 已接入 | 沪深 300/中证 500；对外已去 PE，只出利差分位 |

### 1.2 合成指标

| 指标 | 实现位置 | 真实状态 | 备注 |
|---|---|---|---|
| 综合温度（多源加权合成） | `service._compute_composite_temperature` / `get_overview` | ✅ 已落地 | 韭圈儿恐贪/中长期/且慢/有知有行/集思录/东财/自算股债利差 加权；缺源时重归一权重 |
| 温度分档（short/medium/long） | `service._band_temperature` | ✅ 已落地 | 偏低/适中/偏高（实际阈值与命名可复核） |

### 1.3 乖离率（自算·趋势动量维度）

| 模块 | 实现位置 | 真实状态 | 备注 |
|---|---|---|---|
| 计算引擎 | `bias/calculator.py` | ✅ 代码完整 | 纯函数 `logbias` + `BiasCalculator` + `PriceFetcher`（进程内+文件缓存+回退旧数据标 `stale`） |
| 数据源覆盖 | `bias/calculator.py` | ✅ 代码完整 | index/etf/fund/fund_cum/stock 五类；`bias_to_position` 映射 0–100 波段位置 |
| 品种配置 | `bias/provider.py` + `bias_products.json` | ✅ 代码完整 | 默认行业+宽基；用户可增删持有的基金 |
| 落库链路 | `bias/job.py` → `service.save_multi_items` | ✅ 已打通 | 2026-08-02 修复了 `save_multi_items` 入参结构不匹配导致整表为空的 bug（见 `overview-bias-stale` 文档） |
| **自动跑（同步任务）** | `jobs.py` `SKIP_BIAS` | ✅ **已放开** | `SKIP_BIAS = False`（2026-08-05）；数据源由 akshare/东财改为直连（`bias/direct_feeds.py`，腾讯行情/东财 push2his），直连失败降级 `stale` 不阻断主流程 |

> 结论：乖离率**引擎已完整实现并验证可算**，但**未进入每日自动同步**。当前 `market_multi_items` 表仅在手动/测试触发时可能有数据。

### 1.4 存储层

| 表 | 模型位置 | 真实状态 | 备注 |
|---|---|---|---|
| `market_single_values`（单值，永久） | `domains/temperature/models.py` | ✅ | `source/name/collected_at` 唯一键，幂等 |
| `market_composites`（复合，保留 1 年） | 同上 | ✅ | JSON 列存原始数据 |
| `market_multi_items`（多维列表，保留 1 年） | 同上 | ✅ | 预留 bias / industry_crowding / sector_flow |
| 综合温度落库 | `service.get_overview` | ✅ | 合成值在 overview 接口返回（非独立落库表） |

> 注：v1 的 `store.py`（SQLite 长表 `metric_snapshot/indicator_meta/run_log`）**已被 SQLAlchemy 三表取代**，不在仓库内。

### 1.5 前端

| 视图 | 位置 | 真实状态 | 备注 |
|---|---|---|---|
| 温度/探市页 | `frontend/src/views/temperature/`、`frontend/src/views/explore/` 温度区 | ✅ 已实现 | 含温度三色 token（`--temp-low/mid/high`，与涨跌色物理隔离）、综合温度 hero、来源条、免责声明（见 `temperature-redesign.md`） |
| 乖离率展示 | `temperature/index.vue` 乖离度表 | ✅ 已实现 | 含「数据滞后」横幅 + 每行「滞后」标签（2026-08-02 加） |
| 类型契约 | `frontend/src/api/temperature.ts` | ✅ | `MultiItemsResponse` 含 `stale` 字段 |

---

## 二、待办 / 路线图（按真实状态重排）

优先级沿用 v1 文档的 P0/P1/P2，但**状态以仓库为准**。

### P0（稳定性 · 立即做）

| 项 | 真实状态 | 行动 |
|---|---|---|
| **乖离率接入每日同步** | ⚠️ 引擎完成但 `SKIP_BIAS=True` 禁用 | 定位 `calculator/job` 运行时报错根因 → 修复 → 置 `SKIP_BIAS=False` |
| 定时刷新（cron / systemd timer） | ❌ 未见调度配置 | 加每日收盘后 `TemperatureJob` 调度；当前仅 `jobs.py` 有 `SyncJob` 基类，缺外部触发 |
| 东财成交额重试/超时调优 | ⚠️ 偶发 stale | 已在 fetcher 内 try/except 标灰，需加重试退避降低单点失败 |
| 韭圈儿/akshare 限流降级 | ⚠️ 部分 stale | `calculator.PriceFetcher` 已有文件缓存+回退；备用源（腾讯/新浪）已源码核实但**未实现**，待退出代理后实网验证 |

### P1（精度 · 近期做）

| 项 | 真实状态 | 行动 |
|---|---|---|
| **行业拥挤度** `industry_crowding` | ❌ **未接入**（已从 fetchers 移除，仅模型注释提及） | 重写进 `market_multi_items`；三路径选优（Tushare>baostock>legulegu）+ 分母缓存兜底 |
| **富来智投**资金面（龙虎榜） | ❌ **未接入**（已从 fetchers 移除） | 待 `FULAI_TOKEN` 探测 `out/dlzc` 正确路径；做成可选源 |
| 持仓集中度精确分母（趋近外部 31.2%） | ❌ **未实现** | 见 §三·C，需重做并接入 |
| 股债配比建议输出 | ❌ 未实现 | 由股债利差分位映射股:债，低成本 |

### P2（增强 · 按需求）

| 项 | 真实状态 | 行动 |
|---|---|---|
| **微信日报推送** `notify_wechat` | ❌ **未接入仓库**（v1 文档称 PushPlus 就绪待 token） | 需新建后端推送模块，接 `get_overview` 输出 |
| 持仓集中度历史序列（对照 23.2/34.5/23.9） | ❌ 未实现 | 补建多季度缓存画折线 |
| UI 增强（趋势迷你折线、恐贪历史分位） | ❌ 未实现 | 前端迭代 |
| 数据质量看板（各源新鲜度/stale 计数） | ❌ 未实现 | overview 接口已有 stale 信息，前端未聚合展示 |
| 源分歧提示（多源温差告警） | ❌ 未实现 | 纯工程，可基于已落库数据做 |
| 定时任务失败告警 | ❌ 未实现 | 与 P0 定时刷新配套 |

### 韭圈儿 Pro 自建扩展（文档第九节，整体未启动）

| 批次 | 内容 | 真实状态 |
|---|---|---|
| B0 前置 | 持仓录入模块 `holdings.csv` | ❌ 未实现 |
| B1 提醒闭环 | 回撤提醒 + 策略提醒 + 微信推送 | ❌ 未实现 |
| B2 持仓诊断 | 组合诊断 + 基金持仓估值 | ❌ 未实现 |
| B3 情绪扩展 | 行业恐贪 + 大小盘/成长价值 + 情绪面板 9 维 | ❌ 未实现 |
| B4 工具补全 | 相关性/历史叠加/筛选 | ❌ 未实现 |

---

## 三、关键差距与风险（务必知悉）

### A. 文档标注"已完成"但仓库未接入的项

| 文档声称 | 仓库真实情况 |
|---|---|
| 行业拥挤度 ✅ 工程闭环 | 已从 `fetchers` 移除；`market_multi_items` 仅注释预留，**无代码落地** |
| 主动基金持仓集中度（抱团度）✅ 已跑通（25.01%） | **仓库无 `fund_concentration.py`**；该结论仅存在于 v1 独立脚本，未迁移 |
| 微信日报 ✅ 就绪待 token | **无 `notify_wechat.py`**；后端无推送模块 |
| Web 仪表盘 `index.html` ✅ | 已被 Vue 前端取代（`views/temperature` + `explore`） |
| 落库 `store.py`（SQLite 长表）✅ | 已被 SQLAlchemy 三表取代 |

### B. 乖离率"已实现并启用"

引擎、job、落库、前端展示**全链路代码都在**。2026-08-05 起数据源由 akshare/东财改为直连（`bias/direct_feeds.py`，腾讯行情/东财 push2his），`jobs.py::SKIP_BIAS` 已置 `False` 放开每日同步；直连+兜底失败时单品种标 `stale` 或整批为空，不阻断主流程。待实网跑一次温度同步确认 `market_multi_items` 落库（见 `docs/spec/roadmap.md` §2.1）。

### C. 持仓集中度（抱团度）的方法论结论（v1 实测，仍有效）

- 自算口径：2025Q2 = **16.86%**、2026Q2 = **25.01%**（方向：抱团加深、信息技术/AI 光模块主导）。
- **未复现**你引用的外部口径 **31.2%（2025Q2）**；主因是免费数据分母近似偏低，结论已在 v1 文档透明披露。
- 如需逼近 31.2%，需接入各基金季报"资产配置-股票市值"精确值（当前 `zcpz`/`HYPZ` 接口对近季不稳）。
- **此能力未迁移进 v2 后端**，是待办 P1 里工作量最大的项之一。

### D. 韭圈儿端点之争（结论仍有效，已落地）

- 正确端点 `apiv2.jiucaishuo.com/site/indexes`（POST `{}`）——**已在 `JiucaishuoFetcher` 落地为优先路径**。
- `v2/kjtl/*` 加密密文端点已证不可用 —— v2 代码未使用。

---

## 四、方法论 / 口径结论（从长文档提炼保留，避免丢失）

1. **不自造温度**：优先官方接口；单源失败只标灰（`stale`），不阻塞整体。
2. **韭圈儿**：POST 明文接口优先，Playwright 仅降级。
3. **股债利差**：`利差 = 1/PE − 10Y国债 + 0.3×CPI同比`，历史百分位为估值分位；沪深 300 作整体代理。
4. **乖离率**：`LOGBIAS = (ln(close) − EMA20(ln(close)))×100`，自然对数 + EMA；阈值 ±15/+5/0/−5；等价覆盖爱基金「净值波动/低位区/波段掘金」（不自接同花顺专有接口）。
5. **行业拥挤度**：`(行业PB / 全A中位PB) 历史百分位`；分母三路径健壮兜底。
6. **持仓集中度**：前 50 热门股市值 ÷ 主动基金股票总市值；免费口径偏低，方向可信。

---

## 五、下一步建议（精简行动清单）

1. **先解乖离率开关**：定位并修复 `bias` 运行时报错 → `SKIP_BIAS=False` → 验证每日同步落库。（P0，投入最小、可见度最高）
2. **加定时刷新**：每日收盘后触发 `TemperatureJob`，避免"数据慢几天"。
3. **迁移行业拥挤度进 v2**：复用 `market_multi_items`，接回 `fetchers`。
4. **视 token 情况补富来智投 / 微信推送**。
5. **持仓集中度**：决定是否投入（P1 最大工作量），并在 v2 重做 `fund_concentration` 接入。

---

## 附：本文与两份原始长文档的关系

- 原始「技术文档与任务规划书」≈ v1 工具的**完整方法论 + 任务规划**，含 `fund_concentration` 实测结论。
- 原始「总文档」≈ 同一工具的**更早期总览版**（缺 `fund_concentration`/乖离率独立章节）。
- 本文 = **以 v2 仓库真实代码为准的状态快照**，修正了两者在"已完成/未接入"上的脱节，是后续开发的依据。原始方法论（§四）从长文档提炼保留，避免知识丢失。

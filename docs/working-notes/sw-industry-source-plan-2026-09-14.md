# 申万行业单源接入方案（#1431 换源 + #891 / #892 收口）

> 日期：2026-09-14
> 关联：#1431（温度/行业拥挤度数据取不到：东财通道不可达）、#891（baostock 分母兜底）、#892（行业拥挤度多维升级）
> 输入材料：调研包 `duobeibei_research_20260914`（东财限流与数据源调研 / 申万行业拥挤度乖离率计算 / `industry_metrics.py` / 快照）
> 状态：**待决策点确认后开工**（决策项见 §五）

---

## 一、本机实测（2026-09-14，非推断）

| 验证项 | 调用 | 结果 |
|---|---|---|
| 申万行业清单 | `ak.sw_index_first_info()` | ✅ **31 行**，2.8s（akshare 底层实走 **legulegu** `/stockdata/sw-industry-overview`） |
| 申万行业日线 | `ak.index_hist_sw('801010')` | ✅ **6455 行**，1.0s，字段 `日期/开盘/收盘/最高/最低/成交量/成交额`，最新 **2026-09-14（当日）** |
| 单行业耗时 | 1.0s 请求 + 0.25~0.6s 抖动 | 31 行业串行约 **45~60s**，每日一次可接受 |
| 行业清单口径比对 | akshare 31 vs `bias/constants.py` 32 | 本地多出 **`801020`「采掘」**（2021 版已拆为煤炭 `801950` + 石油石化 `801960`） |

**结论**：申万宏源官网通道在本机**可用且数据到当日**，调研包「不碰东财、纯申万单源」的路线在数据源侧成立。

---

## 二、三处事实更正（issue 描述与代码现状不一致）

1. **#1431 正文提到的函数名在当前代码中已不存在**：`_em_amount_rank()` / `_em_two_dim()` → 实际为
   `_amount_ratio_rank()`（成交额占比分位，**已迁至中证指数官网**）、`_turnover_rank()`（换手率分位，**唯一仍走东财**）、
   `_extra_dims()`（合并两维）。即「成交额维依赖东财」这一缺口**已经部分闭环**，剩余缺口比正文描述更聚焦。
2. **温度计页已收敛进探市页**：前端实际路径为 `frontend/src/views/explore/`（`components/detail/CrowdingTable.vue`、
   `BiasTable.vue`、`MetricDetailTable.vue`），**不存在** `views/temperature/`。
3. **行业清单 31 vs 32**：`bias/constants.py` 实际 **32** 条（注释却写「31 个行业」），比申万现行清单多出过时的 `801020`「采掘」。

---

## 三、现状盘点：哪些源可用、哪些仍卡东财

### 已可用（不经过东财）

| 用途 | 现用源 |
|---|---|
| 全市场成交额 | 东财 push2 主 + **新浪兜底** |
| 全 A 中位 PB（拥挤度分母） | legulegu → 本地缓存 `data/all_pb.csv` → **baostock**（#891 已接入）→ 东财实时 |
| 成交额占比分位 | **中证指数官网**（`stock_zh_index_hist_csindex`） |
| 乖离度（bias） | 行业→**申万官网**；股票/ETF/宽基→**腾讯**；东财仅最后兜底 |
| 新鲜度守卫 | `TemperatureService.get_overview()` 输出 `freshness{latest, age_days, stale, threshold_days=5}` ✅ |

### 仍卡东财（3 处，均不阻断主链路）

1. **换手率分位**（`_turnover_rank()` ← `_em_industry_hist()` → `push2his.eastmoney.com`）：中证官网不提供换手率，
   **东财是唯一源** → 东财不可达时该字段为 `None`，`_record()` 在 `note` 标注，前端显示空值。
2. **东财实时 PB 兜底**（`_eastmoney_current_median_pb()`，push2 f23）：兜底链最后一级，注释已标「出口 IP 被封，实际不可用」。
3. **成交额主源**仍首选东财（有新浪兜底，实测可恢复）。

---

## 四、方案：申万单源接入

### 4.1 新增模块 `backend/app/services/thermometer/sw_industry_source.py`

对齐调研包 `industry_metrics.py` 的口径与健壮性参数：

- `list_sw_industries()`：`ak.sw_index_first_info()` → 31 行业；与 `bias/constants.py` 比对并**告警差异**（决策 D）
- `fetch_sw_daily(codes)`：串行抓取 `ak.index_hist_sw`，单源间隔 `random.uniform(0.25, 0.6)` 秒 + 指数退避（最多 3 次）
- `compute_turnover_share(amount)`：横截面占比 = 单行业成交额 / 31 行业成交额之和
- `compute_share_rank(share, window=250)`：滚动 250 交易日百分位（`min_periods=20`）
- `compute_bias(close, windows=(6, 20, 60))`：`(close − MAn) / MAn × 100`
- 全部**只用 `收盘` + `成交额` 两个字段**，不依赖换手率 / 流通股本 → 天然绕开东财

### 4.2 接线 `industry_crowding.py`

- **成交额占比分位**：申万自算为**主源**，中证官网降为备源（失败自动降级，绝不抛异常打断 `TemperatureJob`）
- **换手率分位**：保留东财兜底；失败置 `None` 并在 `note` 说明（前端已支持空值渲染）
- **PB 分位**：不动（legulegu + baostock 兜底）
- `_record()` 的 `data` 字段**只增不改**，保持 API 向后兼容

### 4.3 前端（参照 `docs/design/` 既有规范）

- `CrowdingTable.vue`：列口径说明更新（成交额占比分母 = 31 行业之和，与中证全指口径的差异）
- `BiasTable.vue`：**修正滞后文案**（现写「东财行情接口暂不可用」，与实际源已改为申万/腾讯不符）
- 沿用既有 design token（`--color-rise` / `--color-fall` / `--bg-card` / `--border-light` 等），不新增硬编码色值

### 4.4 落库验证（#1431 待办第 4 条）

本机 `pdm run scheduler --job temperature --no-jitter` 实跑后核对三表：

```plain
market_single_values / market_composites / market_multi_items
  └─ market_multi_items: source='industry_crowding' 应有 31 行（现为 0 行）
```

同时借同一次实跑建立 `data/all_pb.csv` 缓存，闭环 #891（代码已接 baostock，此前仅因未跑过而缓存为空）。

---

## 五、待拍板的决策点（影响展示口径，需产品侧确认）

| # | 决策点 | 结论（2026-09-14 产品侧确认） |
|---|---|---|
| **A** | 成交额占比分位口径 | **申万主 + 中证备**：默认走申万自算（分母 = 当日纳入的 31 个申万一级行业成交额之和，250 日滚动窗口）；申万缺失时回退中证官网（全历史口径）。来源写入 `data.amount_src` 供排查，前端不区分 |
| **B** | 换手率分位列 | **保留并列空**：东财不可用时显示空值 + 滞后提示，待日后有稳定/付费源再填 |
| **C** | BIAS 窗口口径 | **按调研包口径计算**：`BIASn = (收盘 − MA_n) / MA_n × 100`，n ∈ {6, 20, 60}（简单算术均线）。与既有 `bias/calculator.py` 的 `LOGBIAS`（对数 EMA20，阈值 ±15/±5）**并存、互不替代**：行业维度 BIASn 随拥挤度记录下发；LOGBIAS 的信号语义本轮不动（整体切换需单独评估阈值重定标） |
| **D** | 行业清单 | **对齐申万现行 31 个**：剔除 2021 版已拆分的过时条目 `801020`「采掘」（拆为 `801950` 煤炭 / `801960` 石油石化），补入 `801970` 环保 / `801980` 美容护理；`bias/constants.py` 与 `thermometer.SW_INDUSTRY` 同步修正 |

---

## 六、推进顺序

| 阶段 | 内容 | 状态 |
|---|---|---|
| 1 | 本文档 + 决策点确认 | ✅ 决策已回填（§五） |
| 2 | 后端新增申万单源模块 + 单测（离线，不打网络） | ✅ `sw_industry_source.py` + 20 个离线用例 |
| 3 | 接线 `industry_crowding.py`（申万路径 + 降级链）+ 回归测试 | ✅ `_sw_share_records()` + PB 缺失降级；bias/thermometer 相关 99 passed |
| 4 | 本机实跑验证（数据可用性 + 数值合理性） | ✅ 见 §七（31/31 行业，未落库） |
| 5 | 前端列口径与文案修正 + BIASn 展示 | ⏳ 待做（参照 `docs/design/`） |
| 6 | 实跑落库核对（含 #891 分母缓存建库）与文档收口 | ⏳ 待做（`thermometer/README.md` / `tech-debt.md` / #1431 留痕） |

## 七、本机实跑验证（2026-09-14）

`sw_industry_source.fetch_sw_metrics()` 实跑（未落库，仅验证取数与口径）：**31/31 行业全部取到**，
数据日期 **2026-09-14（当日）**，全程走 `www.swsresearch.com`（零东财请求）。节选：

| 行业 | 成交额占比 | 占比分位 | BIAS6 | BIAS20 | BIAS60 |
|---|---|---|---|---|---|
| 有色金属 | 4.43% | **3.6** | — | −4.72 | — |
| 房地产 | 0.59% | **4.4** | — | −2.45 | — |
| 农林牧渔 | 2.18% | **97.2** | −3.82 | 0.37 | 6.97 |

**数值合理性**：有色金属成交额占比 4.43%（绝对占比不低）但分位仅 3.6 —— 正说明
「分位只与自身历史比」的口径生效（它常年高占比，当下未达自身历史极值），与调研包
对「电子占比 24.7% 但拥挤度仅 68」的解释同型。与调研包 2026-09-11 快照交叉印证：
该快照「最拥挤前三 = 建筑材料 100 / 农林牧渔 97.6 / 通信 96.4」，本次实跑农林牧渔 **97.2**，
口径与量级一致（两日差异属正常波动）。

待办：把该路径接入每日调度后**核对落库行数**（`market_multi_items` 的 `industry_crowding`
应从 0 行变为 31 行），并同步建立 `data/all_pb.csv` 缓存以闭环 #891。


与 **#1434** 的关系：**并联**，不是串联的两步——本方案解决「取不到」（数据源），#1434 解决「没人跑」（调度）。
两者都闭环后，M0 硬指标「探市页可用 / 温度计页可用」（`docs/spec/launch-priority-baseline.md` §一）才真正达成。

---

## 附：调研包结论的可复用增量

| 调研包内容 | 与现状的关系 |
|---|---|
| 申万官网「收盘 + 成交额」自算占比分位 | **增量**：可作为成交额占比分位的主源，单源、零东财 |
| BIAS6 / BIAS20 / BIAS60（简单 MA） | **部分增量**：现有只有 LOGBIAS（对数 EMA20）；6/60 窗口为新口径（决策 C） |
| 「换手率需流通股本、故用占比替代」 | 与现状互补：现状保留东财换手率维（不可用即空），调研包选择不做该维 |
| 东财限流「分域名、按源 IP 突发配额」的结论 | 与 #1431 隔离实验一致，支持「换源 + 长退避」而非「硬扛」 |
| 调度放 GitHub Actions（出口 IP 干净） | 与 #1434 / `data-refresh-scheduling-plan-2026-09-13.md` 结论一致 |

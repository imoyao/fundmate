# 行业拥挤度 · 多维升级设计（2026-08-08）

## 背景与目标

现有行业拥挤度 `industry_crowding.py` 只输出**单维** =「PB 倍数 / 全 A 中位 PB」的历史百分位（`crowding_pct`），
仅反映"行业贵不贵"（估值视角），未覆盖「资金挤不挤」的成交热度。

本轮目标：把拥挤度从单维扩为**三维并列**，均以历史百分位呈现（口径贴近市场通用做法）：

1. **PB 倍数百分位**（现有，估值视角）
2. **成交额占比百分位**（该行业成交额 / 全 A 成交额占比的历史分位）
3. **换手率百分位**（行业等权换手率的历史分位）

**明确不做**（决策 2026-08-08）：

- 60 日线上占比 / 60 日新高占比：需逐成分股 60 日历史（数千次 K 线请求，按日跑成本不可承受），
  且信号与现有乖离率（EMA20 偏离）高度重叠，收入比低，**P2 论证后再定、默认不做**。
- 百万大单净买入：依赖 L2 / 资金流明细，多为付费或被反爬，免费源不齐备，明确不做。
- 热门赛道（AI / 机器人 / 低空等）：无现成成分股定义，维护成本高，不做。

范围口径（用户裁决）：

- 合并**并列三维**，不硬造 0-100 综合拥挤度（市场无公认加权合成公式）。
- 前端**仅温度计页**扩列展示；探市页保持用户漏斗定位、不动。
- 数据源优先用 legulegu 现成算好的分位值，避免自囤长历史。

## 数据源与字段

优先复用 legulegu 现成拥挤度接口（免费、无需 token 之外鉴权，与现有
`ak.stock_a_all_pb()` / `industry_pb_legulegu` 同源）：

| 维度 | legulegu 页面 / 接口 | 口径 |
|---|---|---|
| 成交额占比分位 | `sw-amount-ratio`（申万一级成交额占比） | 行业成交额 / 全 A 成交额占比的分位数 |
| 换手率分位 | `sw-congestion`（行业拥挤度-申万 1 级，指标 1） | 各申万行业等权换手率分位数 |
| PB 倍数分位 | 现有 `index-basic-pb`（`industry_pb_legulegu`） | 行业 PB / 全 A 中位 PB 的历史百分位（已实现） |

**前置验证项（实施第一步，验收卡口）**：

1. 实测 AKShare 是否提供申万一级「行业拥挤度」/「成交额占比」现成函数。
2. 若无现成封装 → 复用 `industry_crowding.py:256-264` 的 `_legulegu_token()` 机制，
   仿照 `industry_pb_legulegu` 自写对 `sw-congestion` / `sw-amount-ratio` 的 HTTP 封装。
3. 确认 legulegu 返回的行业口径与申万一级 31 行业（`bias/constants.py:17-50`）可对齐映射；
   若覆盖非全部，缺失行业走 `_placeholder` 整组标灰降级，绝不抛异常阻塞主链路。

### 历史分位窗口

- **不自己攒历史**：legulegu 自带 2010+ 长历史回算好的分位值，直接取现成的当天结果。
- 规避冷启动：「自今日起每日累计导致初期分位无意义」的问题不复存在（分位由源站长历史算）。
- 参考价值：1~2 年才有判别力（一个牛熊半周期），3 年较稳；legulegu 2010+ 直接满足。

## 存储结构变更

`market_multi_items`（`domains/temperature/models.py:80-107`）每行业一条 `data` JSON，
**表结构不变，仅扩 `data` 字段**（无迁移成本）：

```json
data: {
  // 现有（保留）
  "crowding_pct": ..., "multiple": ..., "ind_pb": ..., "mkt_pb": ...,
  "history_days": ..., "hist_ok": ..., "note": ...,
  // 新增
  "amount_pct": 1.23,        // 行业成交额占比 (%) 当期值
  "amount_pct_rank": 88.0,   // 成交额占比 历史百分位
  "turnover": 2.40,          // 行业换手率 当期值
  "turnover_rank": 75.0,     // 换手率 历史百分位
}
```

频率不变：每日快照，`market_multi_items` 保留 1 年（`service.py:609-635` 已清理）。

## 计算链路

`fetch_industry_crowding()`（`industry_crowding.py:468-520`）保持返回 flat multi 记录，内部扩展：

1. 拉取三维分位（PB 复用现链路；成交额占比 + 换手率经 legulegu，前置验证后定直连/akshare）；
2. 缺失任一维 → 保留现有降级策略，`_placeholder()` 标灰，绝不阻塞 `TemperatureJob` 主链路；
3. 沿用每日 `temperature` job 顺带执行（复用 `_cached`，不新增独立高频任务）。

## API 契约（尽量冻结）

- `GET /api/temperature/overview` — 不变，`multi` 仍含 `industry_crowding`。
- `GET /api/temperature/multi?source=industry_crowding` — 同现结构，`data` 内字段增多，**无破坏**。
- 前端温度计页拥挤度表（`temperature/index.vue:225-352`）扩 2 列：成交额占比分位 / 换手率分位。

## Redis 预留（架构决策，本期不实现）

预约 `backend/app/core/cache.py` 的 `CacheService` 薄接口：

- 本期实现后端为文件/lru（复用 `fetchers.py:91 _cached` 模式），Redis 作为可选后端实现但默认关闭。
- 挂 Hook 点：合成后的拥挤度结果缓存（冷启动加速）。
- 边界：仅缓存自建分析结果与公开行情；家庭核心账本数据不进任何缓存（遵循 AGENTS.md 数据分级、
  AGENTS.md 数据分级）。关于迁移：CacheService 为框架无关薄接口，Flask→FastAPI 不受影响
  （不采用绑 Flask 的 Flask-Caching，避免迁移作废）。

## 本机验证清单

1. AKShare/legule 行业拥挤度接口实测可用，返回与申万一级映射可对齐。
2. 单行业手动算三维分位，比对量级合理（vs 官网 sw-congestion）。
3. `pdm run invoke test`（单进程）+ 前端 `pnpm typecheck` 零错误。

## 待办分派（下一步实施计划）

1. **前置验证**：实测 AKShare 行业拥挤度函数；缺则自写 legulegu HTTP 封装 + 映射校准。
2. 扩展 `industry_crowding.py`：新增两维分位抓取与 `data` 字段。
3. 前端温度计页扩 2 列（沿用设计 token，涨红跌绿，禁止硬编码 hex）。
4. 落 `core/cache.py` 的 `CacheService` 薄接口（本期文件后端，Redis 预留）。
5. 冷启动 / 源不可达：标灰降级，阻塞主链路。

任一环节实测失败按第 2 步方案回退，不扩 Scope。

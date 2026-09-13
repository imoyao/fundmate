# 且慢投顾组合元数据注册表与自动抓取（2026-09-13，#1468）

## 一、背景与目标

此前系统只建档 **2 只**且慢组合（`scripts/seed_advisors.py` 里手写的 `SEED` 列表），
组合的名称 / 主理人 / 风险等级 / 收益指标全靠一次性人工调研，库里大部分是空的
（例如 `ZH013136` 的 `name` 直接就是代码本身）。每次做数据迁移都要重新调研一遍。

本次把调研清单里的 **100 只**且慢组合 + 既有 2 只，落成仓库内的**元数据注册表**，
并接上且慢官方 MCP 的实时抓取，做到「组合清单只维护一处、指标自动刷新」。

## 二、关键发现

### 2.1 且慢 MCP 有 `GetStrategyDetails`（此前未接）

端点为 `stargate.yingmi.com/mcp/v2`（与温度计同 `QIEMAN_API_KEY`）。
`tools/list` 共 **69 个**工具，投顾相关可用工具：

| 工具 | 用途 |
|---|---|
| `GetStrategyDetails` | **组合概览**：名称 / 管理人 / 风险等级 / 成立日 / 简介 / 策略描述 / 净值 / 区间收益 / 回撤 / 波动率 / 夏普 / URL |
| `BatchGetStrategiesComposition` | 当前基金级持仓（已用于 #1392） |
| `BatchGetPoTradeComposition` | 当前「交易成分」（目标交易清单，**非历史**） |
| `GetStrategyRiskInfo` / `BatchGetStrategyRiskInfo` | 策略风险 |
| `GetStrategyBenchmark` | 业绩基准 |
| `GetStrategyAssetClassAnalysis` | 大类资产分布（穿透） |
| `StrategySearchByKeyword` | 关键词搜索组合 |

实测 `GetStrategyDetails` 支持一次传多个 `strategyCodes`（`pageSize` 上限 100，
**不传 pageSize 默认只回 20 条**，会被静默截断），单条返回 24 个字段。

**⚠️ 且慢 MCP 没有「历史调仓」接口** —— 只有当前持仓，以及每只持仓自带的「调仓时间」。
调仓历史只能由我们自己的快照序列推导（见 §四）。

### 2.2 两个真实 bug（原「把代码塞进列表就能跑」不成立的原因）

1. **平台判定用代码前缀**：`advisor_portfolio_job` 里以 `code.upper().startswith('ZH')`
   判定且慢。但清单里有 **8 个非 `ZH` 命名空间**的且慢码
   （`LONG_WIN`、`LONG_WIN_S`、`J7`、`WALLET`、`SI000090`、`SI000035`、`SI000107`、`SI000186`），
   会被误送进**天天基金**适配器，静默抓错或抓空。
   → 改为按 `AdvisorPortfolio.platform` 判定，库内未建档的再用注册表兜底。
2. **`TiantianAdvisorAdapter` 缺 `get_name()` / `get_version()`**：
   `orchestrator._save_sync_log()` 写审计日志时抛 `AttributeError`，
   导致**整个 job 报「同步失败」**（数据其实已落库，但 CLI 返回失败、审计缺失）。
   → 补齐两个方法。

### 2.3 表结构缺口

`advisor_portfolios` 没有波动率 / 夏普 / 四笔钱 / 产品类型 / 净值 / 组合链接 / 策略简介等列，
「补充信息」无处可落。

## 三、落地内容

| 变更 | 位置 |
|---|---|
| **元数据注册表**（102 条，单一真相源） | `backend/app/domains/funds/advisor_catalog.py` |
| 抓取 `GetStrategyDetails`（分批 + 归一化） | `QiemanFetcher.fetch_strategy_details` |
| 适配器暴露概览 | `QiemanAdvisorAdapter.fetch_overview` |
| 工具常量 / 中文字段映射表 | `app/services/thermometer/constants.py` |
| 11 个新列 + 幂等迁移 | `app/domains/funds/models.py`、`app/core/migrations.py` |
| 平台判定修复 + 概览落库 + 调仓推导 | `app/services/sync/jobs/advisor_portfolio_job.py` |
| 注册表 → 建档 | `scripts/seed_advisors.py`（读注册表，不再手写清单） |
| 自选投顾接口暴露新字段 | `app/domains/watchlist/{schemas,views}.py` |
| 调仓操作词表收口 | `app/core/constants.py::ADVISOR_ADJUST_OP_NAME` |
| 前端接线（类型 / 列 / 渲染器 / 抽屉） | `frontend/src/api/watchlist.ts`、`views/asset/watchlist/columnDefs.ts`、`columnRenderers.tsx`、`columnRenderers.css`、`components/WatchlistQuickViewDrawer.vue` |
| 调仓 / 持仓只读接口 | `app/domains/funds/views.py`（`_f()` + 两个 GET）、`tests/domains/test_advisor_views.py` |
| 前端消费明细接口 | `frontend/src/api/funds.ts`（类型 + 两个请求函数） |
| 投顾同步接入每日调度 | `app/services/daily_scheduler.py`、`backend/.env.example`、`docs/dev/scheduler-tasks.md` |

### 存储格式决策：为什么用 Python 常量，而不是 JSON / YAML

- backend **未安装 `pyyaml`**（实测 `ModuleNotFoundError`），YAML 要新增依赖 + 确认打包；
- 仓库既有惯例就是 Python 常量（`scripts/seed_core_indices.py` 的 `CORE_INDICES`、
  `app/core/constants.py`、`app/services/thermometer/constants.py`）；
- 注册表需被 seed 脚本与同步任务直接 `import`，Python 模块最省事、类型安全、无打包问题；
- 数据是「纯数据 + 注释」，JSON 不能写注释，反而不如 Python 可维护。

## 四、且慢调仓明细：由快照序列推导

且慢没有历史调仓接口，但 `BatchGetStrategiesComposition` 每只持仓带「调仓时间」，
`_apply_holdings` 又是**按 `as_of_date` 覆盖式快照**，因此：

> 同一组合每同步一次就留一份快照；相邻两次快照的占比之差 = 本次调仓的「前 / 后占比 + 方向」。

实现见 `AdvisorPortfolioSyncJob._derive_qieman_adjust`：

- 取 `max(as_of_date) < 本次` 作为上一快照，与本次逐基金对比；
- `新增`(0→X) / `加仓`(X↑) / `减仓`(X↓，含清仓→0) / `持平`；
- 写 `advisor_adjust_histories`（`source='qieman'`），`reason` 记录推导来源快照日；
- **首次快照无前值可对比 → 不写**（不编造 0→X 的假建仓记录）。

## 五、落库结果（本地 invest.db，2026-09-13）

- `advisor_portfolios`：**105** 只（且慢 **102** + 天天 3）
- `advisor_holdings`：1755 条；且慢持仓基金 963 只，其中 **962 只命中本地 `funds` 表**
  （唯一未命中 `968048` 摩根亚洲股息人民币累计，本地名录暂缺）
- `advisor_adjust_histories`：天天 1159 条 + **且慢 74 条**（4 只有 ≥2 次快照的组合推导而来）
- 且慢新字段填充率（/102）：`strategy_summary` 101、`source_url` 101、`nav`/`nav_date`/`return_1d` 100、
  `volatility`/`sharpe_ratio` 96、`allocation` 102、`product_type` 82
  （缺口均为新成立 / 货币类组合官方本就无该指标）

## 六、前端接线（2026-09-13 补记）

后端字段就绪后，前端「自选 → 投顾组合」侧同步接上，共 4 处：

| 位置 | 内容 |
|------|------|
| `src/api/watchlist.ts` | `WatchlistItem` 补 12 个可选字段（`return_1d/1q/6m`、`volatility`、`sharpe_ratio`、`advisor_allocation(_label)`、`advisor_product_type`、`advisor_strategy_summary`、`advisor_nav(_date)`、`advisor_source_url`） |
| `views/asset/watchlist/columnDefs.ts` | 新增 10 列，均 `appliesTo:["portfolio"]` + `defaultHidden:true`（守 #993「新列默认隐藏」，不冲击 1040px 宽度预算），并登记进 `COLUMN_GROUP_MAP` 的 `portfolio` 组 |
| `views/asset/watchlist/columnRenderers.tsx` | `RENDERER_ADVISOR_RETURNS` 补 `return_1d/1q/6m`；新增波动率 / 夏普 / 净值 / 配置目标 / 产品类型 / 策略简介 / 官方链接分支 |
| `components/WatchlistQuickViewDrawer.vue` | 新增「投顾信息」区（仅 portfolio）：配置目标 / 产品类型 / 组合净值 / **策略简介全文** / 官方页面链接 |

两个刻意的设计取舍：

- **净值日期不开列**：并到「组合净值」列的 `title`（`组合净值（截至 YYYY-MM-DD）`），
  省一列宽度又能交代口径。
- **外部链接做协议白名单**：`safeExternalUrl()` 只放行 `http:`/`https:`，
  后端落库的是外部站点 URL，直接插 `href` 有 `javascript:` 注入风险。
  实测库内 101 条 `source_url` 全为 `https://qieman.com/alfa/portfolio/<code>`。

校验：`vue-tsc --noEmit --skipLibCheck` 通过；`eslint` / `prettier` / `stylelint` 全绿。

## 七、调仓 / 持仓只读接口（2026-09-13 补记）

排查「调仓信息存到哪」时发现一处更根本的缺口：**`advisor_holdings` 与
`advisor_adjust_histories` 此前一直是「只写不读」**——同步任务在落库，但全后端没有任何
接口暴露它们（天天那 1159 条调仓同样如此）。数据存下来了却读不出来，等于还是锁在库里。
补上两个 market 域只读接口（公开参照数据，无需登录）：

| 接口 | 返回 |
|------|------|
| `GET /api/funds/advisors/<code>/holdings/` | 最新快照日的成分基金与占比；每只带 `in_local_db`（是否已收录本地 `funds` 表） |
| `GET /api/funds/advisors/<code>/adjusts/?limit=N&date=YYYY-MM-DD` | 调仓明细，按调仓日倒序分组；`limit` 缺省 10 上限 50，`date` 可精确取某日 |

实现要点：

- **Decimal 必须显式转 float**：`SafeNumeric` 读回是 `Decimal`，Flask 的 JSON provider
  会把 `Decimal` 序列化成**字符串**（不是数字），不转会污染所有数值字段。
- **两步法关联**：`fund_code` 不建硬外键（模型注释：避免组合成分暂缺于本地名录时阻塞写入），
  所以 `in_local_db` 用一次 `Fund.fund_code.in_(...)` 查询比对得出。
- 前端侧：速览抽屉新增「成分与调仓」区，抽屉打开时才拉（105 只组合全量带明细会拖慢列表）。

单测 `tests/domains/test_advisor_views.py`（5 条）：最新快照选取、Decimal→float、
`in_local_db` 两态、按日分组与倒序、limit/date 边界与非法入参、404、空结构不报错。

## 八、把投顾同步接入每日调度（2026-09-13 补记）

排查时发现：`daily_scheduler._JOB_TEMPLATES` 里**只有 `temperature` 和 `fund_nav` 两个任务**，
投顾组合同步不在其中。后果是——且慢的持仓快照不会自动累积，调仓历史会永远停在这次手动跑出的
74 条，`nav` / 收益 / 波动率也不会更新。等于「数据存下来了，但还得手动抓」，与本次目标相悖。

新增第三项（`app/services/daily_scheduler.py`）：

```python
('advisor_portfolio', ENV_ADVISOR_ENABLED, ENV_ADVISOR_CRON, DEFAULT_ADVISOR_CRON, None, ...)
```

两个关键决策：

- **`target_kind` 必须是 `None`，不能是 `'fund'`**：目标池是「组合代码」（`ZHxxxx` /
  `LONG_WIN` / 天天 combo），而 `resolve_targets()` 只产 `fund` / `stock` 两类。套成 `'fund'`
  会拿到空列表——而该 job 空目标不报错，结果是「每天记一条 success 但什么都没同步」的
  **静默空跑**。留 `None` 后 job 内部 `_resolve_targets` 回退库内全部在售 `TIANTIAN + QIEMAN`。
- **cron 定在 22:00（净值 21:30 之后）**：且慢调仓快照带的是当日占比口径，排在净值前会
  用到前一日口径；它同时是且慢调仓历史的唯一来源，落一天就少一天的推导依据。

同步更新的位置：`backend/.env.example`、`docs/dev/scheduler-tasks.md`（任务表 + 配置段）、
`tests/services/test_local_daily_scheduler.py`（原 `job_names()` 断言 + 新增 3 条用例）。

## 九、已知限制与后续

- **调仓历史需时间累积**：且慢调仓明细靠快照序列，只有跑过 ≥2 次且期间有调仓的组合才有记录；
  接入每日调度后会自然补齐。
- `WALLET`（盈米宝）不是策略实体，`GetStrategyDetails` 无记录，仅保留注册表策展字段。
- 6 只组合无收益指标（2026 年新成立 / 货币类），非抓取失败。
- 且慢调仓明细**没有官方接口**，推导出的「调仓日」= 我们快照发现变化的日期，
  与官方实际发车日可能差 1 天（快照频率决定），不是官方口径。
- 仓库本地 git 对象损坏（`git log` 报 `bad object HEAD`，refs 指向缺失对象），
  本次改动未做任何 git 操作，由另一路修复。

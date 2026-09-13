# 探市数据底座 · 方案 B 实施计划（2026-09-13）

**状态**：**已拍板并实施**（方案 B 最小版）。本文是 issue **#1460** 的实施计划，同时收口
`data-refresh-scheduling-plan-2026-09-13.md` 的 **D1 / D2 / D4 / D10** 四项决策。

**关联**：#1460（本 issue）· #1467（本机常驻调度，框架已就绪）· #1436（海外 4 资产缺源）·
#1451（探市口径决策）· #1434（CI 调度）· #821（探市缺口跟踪）

**上游文档**：`data-refresh-scheduling-plan-2026-09-13.md`（盘点 v2，推荐 B）·
`docs/features/market-explorer.md`（20 资产源映射与 §7 job 规划）·
`docs/spec/data-strategy.md`（数据准入四问）· `docs/spec/decisions.md`

---

## 0. 结论先行

1. **方案 B 是最优解，且「最小版」是对的**——见 §1 的三方案对比，B 是唯一同时解决
   「首屏慢 / 跨进程不稳定 / 无历史留痕 / 坏数据不可见」四个问题的方案。
2. **不新建表，复用 `market_multi_items`**（上游 F8 已核，本轮再次逐字段复核通过，见 §2）。
3. **只落「算好的结果」，不落收盘序列**——分位与 σ 由数据源返回的全历史当场现算，
   库内不存多余数据（`data-strategy.md` L3 口径）。
4. **顺带修掉三个问题**（§5）：
   - **F1**：`run_all_jobs()` 的 `execution_plan` 漏 job——**实为漏 5 个**（上游文档记 4 个，
     漏了 `channel_link`，见 §5.1）。
   - **F6**：2 个汇率资产数据停在 2023-11-10——**根因已查明，且不是数据源坏了**：
     `akshare.currency_boc_sina()` 的默认日期区间被上游**硬编码为 `20230304`~`20231110`**，
     调用时未传 `start_date`/`end_date` 就必然拿到 2023 年的 180 行。**显式传日期后实测
     890 行、最新到 2026-09-12**。故上游 D10 的「先降级软占位」**不再需要**，直接修源即可。
   - **D4 最小可用版**：给每日任务加 `calendar` 维度（否则 A 股假期会让标普/纳指/美债/黄金
     停更一周——这正是探市资产要每天更新的理由）。
5. **开关默认 `live`**：合并后线上行为**完全不变**，人工切 `db` 观察后再改默认（§4.3）。

---

## 1. 为什么是方案 B

| 方案 | 做法 | 判定 |
|------|------|------|
| **A 只预热缓存** | 每日 08:00 调一次 `get_overview()` 让缓存热着 | ❌ **治标**。缓存 TTL 30 分钟后照样回源；进程重启即冷（文件层虽跨进程存活，但过期后首个访问者仍要串行拉 12+ 个外部请求）；**无历史、坏数据不可见**——F6 那两个 2023 年的汇率值就是这样活了近两年没人发现 |
| **B 每日落库 + 读库**（**采纳**） | 每日 08:00 抓一次 → 落 `market_multi_items` → 端点读库；实时取数降为「库空」兜底 | ✅ **治本**。首屏毫秒级（读本地 SQLite）；跨进程稳定；有历史留痕（可做「昨天 vs 今天」）；坏数据可见（`stale` + 审计 + 交易日滞后守卫） |
| **C B + 盘中补充** | 再在 A 股 / 港股收盘后各补一次 | ❌ **先不做**。当日涨跌更准，但一天 3 次 × 12 请求，且要处理「同一天两个值」的口径问题；页面当前无盘中诉求 |

**为什么 B 不违背「不引入 Redis」的既有结论**（issue #1460 正文已论证）：这里的瓶颈是
**取数慢**，不是并发；Redis 的 TTL 过期后仍需重拉，而落库是「一次获取、永久复用」。
本项目为单机个人应用，`core/cache.py` 亦写明「单机勿开 Redis」。

**为什么「最小版」不加盘中**：先把「每日新鲜」这条主干打通，盘中是**增量精度**问题，
不是**可用性**问题；先做会同时引入成本翻倍与同日双值口径两个新变量。

---

## 2. 数据模型：复用 `market_multi_items`

上游 F8 的结论本轮逐字段复核通过（`app/domains/temperature/models.py:80-107`）：

| 需求 | `MarketMultiItem` 现成字段 | 说明 |
|------|--------------------------|------|
| 数据源标识 | `source` | 取 `'market_snapshot'` |
| 品种类型 | `item_type` | 取 `'asset'`；债券收益率轨取 `'bond_yield'` |
| 品种代码 | `item_code` | 资产 `key`（`sh000001` / `.INX` / `USD_INDEX` …）；`String(20)` 全部装得下 |
| 品种名称 | `item_name` | 资产中文名 |
| 算好的结果 | `data`（JSON） | `{change_pct, trade_date, data_asof, position, anomaly, caliber}` |
| 数据日期 | `collected_at`（Date） | 落库日（用于幂等与保留期） |
| 失效标记 | `stale` | 取数失败 / 交易日滞后 → `True` |
| 幂等 | 唯一键 `(source, item_type, item_code, collected_at)` | 同日重跑只 upsert 同批行 |
| 保留期 | 既有 `TemperatureService.cleanup_old_data()` 已按 1 年清理本表 | **零新增代码**；由 `temperature` job 调用（`thermometer/jobs.py:308`） |

**为什么 `item_code` 用资产 `key` 而不是中文名**：`key` 是 `ASSET_CONFIG` 的稳定主键
（`.INX` / `sh511010` / `USD_INDEX`），中文名会随文案调整而漂移。

**为什么 `item_type` 用 `'asset'` 而不是分组名**：`item_type` 描述「行的种类」，分组
（A股/港股/…）是展示维度，已在 `data.category` 与代码常量 `ASSET_CONFIG` 里，
落库重复一份只会引入两处口径。

---

## 3. 落什么 / 不落什么（这是本方案最关键的口径）

| 类别 | 数量 | 是否落库 | 理由 |
|------|------|---------|------|
| **可取数资产** | 14 | ✅ 每日一行 | 涨跌 / 分位 / ⚡ 异动都是每日新值 |
| **结构性软占位**（海外 4 + 中证2000 + 比特币） | 6 | ❌ **不落** | 它们是**结构性事实**（无源），不是每日数据；由代码常量 `ASSET_CONFIG` 提供，落库等于每天重复写 6 行常量 |
| **债券收益率轨**（中/美 10Y） | 1 | ✅ 每日一行 | 卡片主数值之一，best-effort 取数 |
| **收盘价长历史序列** | — | ❌ **不落** | 分位与 σ 每次取数时由数据源返回的全历史**当场现算**（实测 12/14 资产 1492~8724 行，远超 500 日窗口）；落序列既无必要也违背 `data-strategy.md`「不存多余数据」 |

**单资产取数失败怎么办**：落 `stale=true` + 错误摘要（**不落上次的值**）。
「展示上次成功值」是**读时**行为——读库路径发现当日行 `stale=true` 时，回退到该
`item_code` 最近一条 `stale=false` 的行，并把结果标 `stale=true` 返回。
这样「今天失败」这件事本身可审计，而页面仍有值可显示。

**交易日滞后守卫（防 F6 类事故复发）**：落库时把每个资产的 `trade_date` 与**同批次的
最大 `trade_date`** 比较，落后超过 `_STALE_TRADE_DAYS = 14` 个自然日即置 `stale=true`
并写入原因。取 14 天是因为 A 股长假（国庆 7 天 + 前后周末）会让 A 股资产的 `trade_date`
合法地落后美股约 9 天，取更小会产生误报；而 F6 那种「落后 2 年」会被立刻抓住。
**这是本方案对「坏数据可见」的兜底**——不依赖任何人工巡检。

---

## 4. 实现

### 4.1 落库 job：`market_snapshot`

新增 `backend/app/services/sync/jobs/market_snapshot_job.py`，继承 `SyncJob`：

- `targets=None` 路径（与 `fund_company_backfill` / `asset_snapshot` 同型）：一次性取
  `ASSET_CONFIG` 全量，不依赖 `resolve_targets()` 的持仓/自选池。
- **复用 `market_service` 的取数与计算**（`_build_asset_item` / `_fetch_bond_yield_10y`），
  不在 job 里另写一套——否则「页面算的分位」与「库里落的分位」会分叉。
- 并发取数沿用 `market_service` 的共享 deadline 机制（#1461 的成果），
  失败项落 `stale=true` 而非中断整批。
- `_allow_empty_data = False`：14 个资产**全部**失败时记一条失败审计（探市快照属
  关键 job，按 D9「连续 1 次失败即告警」口径），避免「静默空跑成功」。
- 幂等：复用 `save_multi_items` 的「同 source 当日先删后插」语义。

**注册**：`DataSyncOrchestrator._register_jobs()` 加 `self.jobs['market_snapshot']`，
并加入 `execution_plan`。

### 4.2 读库路径：`MarketOverviewService`

- `get_overview()` 变为**分派器**，按 `MARKET_OVERVIEW_SOURCE` 选择实现：
  - `live`（**默认**）→ 现行为（`_get_overview_live()`，原实现整体搬入，逐行不变）
  - `db` → `_get_overview_from_db()`；**库内无任何 `market_snapshot` 行时自动回退 `live`**
- **响应结构完全不变**（前端 `api/market.ts` 无需改动），仅**新增两个附加字段**：
  - 顶层 `data_source`：`'db' | 'live'`，用于排障与灰度观察
  - 每资产 `stale`：`bool`，该值是否为「回退的上次成功值 / 交易日滞后」
- `force=true` 语义保持不变（绕过缓存）；在 `db` 模式下解释为「直接走实时路径」。
- **绝不 500**：读库异常、JSON 结构异常、库空，一律降级（回退 live 或软占位）。

### 4.3 开关与回滚

| 开关 | 取值 | 默认 | 作用 |
|------|------|------|------|
| `MARKET_OVERVIEW_SOURCE` | `live` / `db` | **`live`** | 端点取数来源。**合并时默认 `live` = 行为不变**，人工切 `db` 观察后再改默认；出问题一条 env 回退 |
| `SCHEDULER_MARKET_ENABLED` | `true` / `false` | `true` | 单独关掉落库 job |
| `SCHEDULER_MARKET_CRON` | cron | `0 8 * * *` | 落库时点（美股 04:00/05:00 收盘后） |

回滚原则与上游 §9.2 一致：**新增路径 + 开关，不原地替换**。旧实时路径在开关为
`live` 时是**唯一**路径，代码层面也完整保留（不是「删掉后再加回来」）。

### 4.4 调度接入（含 D4 最小可用版）

- `_JOB_TEMPLATES` 增加 `market_snapshot`（08:00，`target_kind=None`）。
- **给 `DailyJobSpec` 加 `calendar` 字段**，取值 `cn`（跟 A 股日历，休市跳过）/ `none`
  （7×24 不跳过）。现有 `temperature` / `fund_nav` 显式标 `cn`（**行为不变**），
  `market_snapshot` 标 `none`——因为它的 20 个资产里有美股 / 商品 / 汇率，
  **A 股放假不等于全球放假**（上游 §3-C）。
  影响面：`_run_job` / `_startup_catch_up` / `catch_up_targets` 三处由「全局布尔」
  改为「按任务判定」。
- `hk` / `us` 两种日历**本轮不做**（上游 D4 的完整版），登记为遗留。

---

## 5. 顺带修复

### 5.1 F1：`execution_plan` 漏 job（**实为 5 个，不是 4 个**）

`_register_jobs()` 实际注册 **21** 个 job，`execution_plan` 只有 **16** 个，
**漏 5 个**：`temperature` · `index_valuation` · `convertible_bond` · `amac_institution` ·
**`channel_link`**。

> **修正上游文档**：`data-refresh-scheduling-plan-2026-09-13.md` §3-A 写「已注册 25 个
> job / 在计划外 4 个」，两个数字都不准——`channel_link`（`orchestrator.py:126` 注册）
> 在原文的「计划内 16」与「计划外 4」两张清单里**都没出现**。以本节为准。

后果：`grab.all` / `pdm run sync --all` / CI 的 `pdm run scheduler` 都不刷新温度计
（连带 `bias` 乖离率、`industry_crowding` 拥挤度），也不刷新可转债条款、指数估值、
AMAC 主数据、跨渠道关联——而 `backend/tasks.py` 与 `sync_cli.py` 的文案都写着
「全部同步任务（元数据 + 温度）」，**文案在骗人**。

**处置**：把 5 个全部补进 `execution_plan`，位置按依赖关系安排，并加注释标明各自的
建议频率。上游 D2 建议的「分组化（每日/每周/每月/每季）」是**后续 PR3** 的事——
它改变 `run_all_jobs` 的语义（「全量同步」到底含哪些），需要同步改文案，不宜与
本 issue 混在一起。本轮只修「漏」，不重构「怎么分组」。

**回归防线**：新增测试断言 `set(execution_plan) == set(orchestrator.jobs)`，
让「注册了却没进计划」这个 bug 无法再复发。

### 5.2 F6：汇率资产陈旧（根因查明，直接修好）

**现象**：`USD_INDEX` / `USDCNH` 只返回 180 行、尾部停在 `2023-11-10`。

**根因**（本轮实测）：

```python
akshare 1.18.91
inspect.signature(ak.currency_boc_sina)
# (symbol: str = '美元', start_date: str = '20230304', end_date: str = '20231110')
```

**默认区间被上游硬编码为 `20230304`~`20231110`**。`ASSET_CONFIG` 里写的是
`'args': ('美元',)`，只传了品种，于是必然拿到 2023 年那 180 行——**不是数据源坏了，
是调用点漏传日期**。

**验证**（显式传日期）：

```python
ak.currency_boc_sina('美元', start_date='20230901', end_date='20260913')
# shape (890, 6)，列 ['日期','中行汇买价','中行钞买价','中行钞卖价/汇卖价','央行中间价','中行折算价']
# 尾部 2026-09-11 / 2026-09-12  ← 数据新鲜
```

**处置**：给 `ASSET_CONFIG` 的这两个资产加 `date_range_years: 3`，由
`_resolve_source_call()` 在取数时注入 `start_date` / `end_date`（近 3 年，
≥500 交易日，满足 500 日分位与 250 日 σ 两个窗口）。

**对上游 D10 的修订**：D10 原推荐「立即降级为软占位 + 另开 issue 查根因」。
**降级不再需要**——修源即可，且两个汇率卡从「展示 2023 年的假当日涨跌」变为
「展示真实新鲜的涨跌 + 500 日分位」。这比置灰更有价值，也更符合「探市要能看」的初衷。

---

## 6. 验收标准

> **实施状态（2026-09-13）**：全部代码与文档已落地，自动化测试全绿，并已**真机端到端跑通**。
> 新增/修改测试文件 6 个，相关用例 **100 passed**（`test_market_snapshot_job.py` 12 /
> `test_market_overview.py` 读库+开关+预热守卫 24 / `test_orchestrator.py` 4 /
> `test_daily_scheduler.py` 8 / `test_local_daily_scheduler.py`）。
> 全量 `pytest -p no:xdist`：**1509 passed + 1 error**，该 error 是 `test_ledgers.py` 在
> 23 分钟单进程长跑中的 `MemoryError`（SQLAlchemy 编译器缓存处 OOM，属机器资源耗尽而非断言失败
> ——单独跑该文件 116 passed 全绿），故全量实为**零失败**。
>
> **真机实测结果**（真实 akshare + 临时 SQLite，**脚本已入库**：
> `backend/scripts/verify_market_snapshot.py`，`cd backend && pdm run python scripts/verify_market_snapshot.py`
> 可复跑，`--keep` 保留临时库手工查库）：
> - 落库 **15 行**、取数成功 **15/15**、失败 **0**、耗时 **11.9s**；
> - 6 个结构性软占位**未入库**；全部 `stale=False`；`collected_at` 唯一；
> - **F6 复验 PASS**：`USD_INDEX` / `USDCNH` 的 `trade_date` = **2026-09-12**（不再是 2023-11-10）；
> - 读库路径 12 次调用：median **0.0ms**、**p95 16.0ms**、max 16.0ms，`data_source=db`、6 个资产组；
> - 过程中**发现并修复一个会 abort 进程的并发缺陷**（V8/py_mini_racer），见 §8 风险第 1 条。

| 项 | 标准 | 状态 |
|----|------|------|
| 首屏耗时 | `db` 路径 p95 < 300ms（本地 SQLite，不含网络） | ✅ 真机实测 **p95 = 16ms** |
| 行为不变性 | `MARKET_OVERVIEW_SOURCE=live`（默认）时，响应与改动前**逐字段一致**（除新增的 `data_source` / `stale`） | ✅ 单测覆盖 |
| 冷启动 | 库空时自动回退实时取数，**不白屏、不 500** | ✅ 单测覆盖 |
| 数据新鲜度 | `data_asof` 每次 08:0x 更新；`collected_at` 为该批次日期 | ✅ 单测覆盖 |
| 降级 | 单资产失败 → 该行 `stale=true` + 读时回退上次成功值；**整体端点永不 500** | ✅ 单测覆盖 |
| 坏数据可见 | 任一资产 `trade_date` 落后同批次最大 `trade_date` >14 天 → `stale=true` | ✅ 单测覆盖 |
| 幂等 | 同日重复跑只 upsert 同批行（唯一键），不产生重复 | ✅ 单测覆盖 |
| 保留期 | 1 年滚动清理（复用既有 `cleanup_old_data`，零新增代码） | ✅ 复用既有实现 |
| 可观测 | `sync_logs` 出现 `market_snapshot` 记录；`pdm run invoke sched.status` 可见 | ✅ 已接入 `execution_plan` 与本机调度（`sync_logs` 由 Orchestrator 写入；直调 `job.run()` 不经 Orchestrator，故真机脚本里无该行属预期） |
| F6 | `USD_INDEX` / `USDCNH` 的 `trade_date` 为最近交易日（不再是 2023-11-10） | ✅ 单测 + **真机实测 trade_date=2026-09-12** |
| F1 | `execution_plan` 覆盖全部已注册 job（有回归测试钉死） | ✅ 双向断言测试 |

---

## 7. 本次范围与后续

**本次（对应上游 PR0 + PR2，并入 F1 与 D4 最小版）**

| 项 | 内容 |
|----|------|
| 落库 job | `market_snapshot_job.py` + 注册 + 进 `execution_plan` |
| 读库路径 | `_get_overview_from_db()` + `MARKET_OVERVIEW_SOURCE` 开关 |
| 调度接入 | `_JOB_TEMPLATES` + `calendar` 维度（`cn`/`none`） |
| F1 | `execution_plan` 补 5 个 job + 完整性回归测试 |
| F6 | 汇率资产显式传日期（修源，不降级） |
| 文档 | 本文 + `decisions.md` + `market-explorer.md` §7 + `data-refresh-inventory.md` §4 + `scheduler-tasks.md` + `.env.example` |

**明确不在本次范围（登记为后续）**

| # | 项 | 归属 |
|---|----|------|
| 1 | `execution_plan` **分组化**（每日/每周/每月/每季）与文案收口 | 上游 PR3 |
| 2 | 本机覆盖面扩到 7 项（`price_history` / `dividend_split` / `asset_snapshot` / JSL 保活…） | 上游 PR1 |
| 3 | `hk` / `us` 日历分组 | 上游 D4 完整版 |
| 4 | 可靠性加固（`misfire_grace_time` 6h→24h、跨天补跑） | 上游 PR4 |
| 5 | 告警通道（本机失败落盘 + 通知） | 上游 D9，依赖通知渠道选型 |
| 6 | 邮件简报等下游消费直接读库 | #1460 P3 |
| 7 | 盘中补充（方案 C） | 页面确有诉求再评估 |
| 8 | 海外 4 资产 / 比特币历史序列 | 已穷举不可得（#1436），软占位是结论 |

---

## 8. 风险

### 8.1 真机实施中发现并已处理

| # | 风险（实测发现） | 处置 |
|---|-----------------|------|
| 1 | **并发取数会 abort 整个进程**：akshare 有 **40 个模块**用 `py_mini_racer`（探市 14 资产里 **11 个**走其中 5 个函数），**每次调用新建一个 `MiniRacer()`**，而 V8 configurable pool 只能初始化一次；`_FETCH_WORKERS=6` 并发首次创建触发 `FATAL: Check failed: !IsConfigurablePoolInitialized()`。**这是 C++ abort，`except Exception` 抓不住**——Web 服务 / 调度器守护进程一起没，不是「某个资产降级」 | ✅ **已修（结构性）**：新增 `app/core/v8_guard.py`（`ensure_v8_ready()`，双检锁 + 结果缓存），挂在**全仓唯一收口点** `get_akshare()` 上 → 任何取数路径自动免疫，无需手动预热；`fetch_snapshot` 另用其返回值决定并发度（失败则 1）。真机对照：单线程 OK / 6 线程 abort(exit 3) / **预热后 6 线程 OK** / **工作线程预热后 6 线程 OK**。**顺带覆盖第二处隐患**：`AkshareAdapter.fetch_stock_price` → `stock_zh_a_daily` 被 `async_backfill` 逐资产起线程调用。测试 `tests/core/test_v8_guard.py` + `TestFetchConcurrencyGuard`。**已升级为平台级硬约束 D24** |
| 2 | **周末汇率卡显示 `+0.00%`**：`currency_boc_sina` 会在**非工作日追加一条顺延行**（实测 `2026-09-12` 是周六，`中行折算价` 沿用周五的 677.43，`央行中间价=NaN`），导致 `_calc_daily_change` 比较「周五 vs 顺延行」得 0.00%，**掩盖周五的真实变动**。两个汇率卡因同源同参（均为 `currency_boc_sina('美元')`，见 #1451 决策）会**同时**显示同一个 0.00% | ⚠️ **未改，仅记录**。属 `live` 路径**原有**行为、非本次引入；影响面是 20 张卡里的 2 张、且仅周末/假期。修法（择一）需产品口径决策：① 计算前剔除尾部「顺延行」（判定信号依赖源特征，较脆）；② 汇率卡改用「最近一次有效观测日」为基准；③ 接受现状。**建议先按 ③ 上线观察** |

### 8.2 设计与实施风险

| 风险 | 缓解 |
|------|------|
| 落库口径与页面口径分叉 | job **复用** `market_service` 的取数与计算函数，不另写一套 |
| 把坏数据固化进库 | 交易日滞后守卫（>14 天置 `stale`）+ 单资产失败置 `stale`；读时不静默 |
| 切 `db` 后页面变「陈旧但无人知」 | 响应带 `data_source` 与 `stale`；`collected_at` 可查；默认 `live` 保证灰度可控 |
| `calendar` 改动影响既有两任务 | 现有 `temperature` / `fund_nav` 显式标 `cn`，行为与改动前一致；有单测覆盖 |
| `execution_plan` 补 job 让 `grab.all` 变慢/失败面变大 | 单 job 失败已被 `_execute_job` 隔离，不中断后续；上游 PR3 的分组化会收敛运行时 |
| `market_snapshot` 默认开启（每天 ~8 次外部请求） | 成本可忽略（15 行/天）；**若默认关**，用户切 `db` 时库空、读路径回退实时而无人写库 → 「开关拨了毫无变化」的静默陷阱，故必须默认开 |

---
title: 数据自动更新清单（分层 · 频率 · 现状 · 缺口）
---

# 数据自动更新清单

**版本**: v1.0
**最后更新**: 2026-09-13
**性质**: 事实标准（成本与现状列均为真库 / 真接口实测，非推断；「现状」列会腐烂，引用前先重跑第 5 节的诊断命令）

> 分层口径（L1~L4）与准入四问定义在 [`data-strategy.md`](./data-strategy.md)，本文**不重复定义**，只登记「哪些数据靠什么刷新」。

## 1. 本文解决什么

「自动化到底跑没跑」此前只能靠人回忆。本文把三件事集中到一处：

1. **谁该被刷新** —— 每个数据项的分层、来源 job、建议频率；
2. **实测成本** —— 接口单次耗时与返回量级（决定「能不能走全量」）；
3. **实测现状** —— 每个 job 最后一次**真正跑起来**是什么时候，以 `sync_logs` 为准。

## 2. 实测成本（2026-09-11 · akshare 1.18.91 · 真接口直连）

| 接口 | 单次耗时 | 返回量级 | 成本性质 |
|------|---------|---------|---------|
| `fund_scale_open_sina()` | 37.3 s | 6,976 × 9 | **全市场单次**，与库内规模无关 |
| `fund_name_em()` | 20.1 s | 27,842 × 5 | **全市场单次** |
| `fund_info_ths(code)` | 0.68 ~ 0.99 s | 18 × 2 | 逐只 |
| `fund_individual_basic_info_xq(code)` | 0.91 ~ 1.07 s | 14 × 2 | 逐只 |
| `fund_portfolio_hold_em(code)` | 1.78 s | 220 × 7 | 逐只 |

**逐只类外推**（按 1.8 s/只含建连）：

| 目标池 | 只数 | 耗时 |
|--------|------|------|
| 用户触达核心池 | 117 | **≈3.5 分钟** |
| `funds` 全库 | 26,938 | **≈13.5 小时** |

> **结论：瓶颈是请求数，不是存储量。**
> 标量字段全量填充只增加几百 KB（`funds` 全表 22 列合计 3.51 MB），而全库逐只抓取是 13.5 小时的外部请求。
> 因此判断「能不能全量」的依据是**单次调用是否产生逐条外部请求**，与目标池大小无关。

## 3. 分层 → 刷新策略

| 层 | 刷新策略 | 允许全量？ | 本项目实例 |
|----|---------|-----------|-----------|
| L1 用户数据 | 用户写入即落盘（非抓取） | — | `positions` / `transactions` / `watchlist` |
| L2 派生计算 | 由 L1 现算，不落盘 | — | 收益 / 盈亏 / XIRR / 资产快照 |
| L3 参考展示 | **按需 + 缓存 + 可降级 `—`** | **仅当单次调用返回全市场列表时** | 规模 / 仓位 / 公司 / 经理 / 全称 / 费率 |
| L4 关联关系 | 按用户触达范围建 | 否 | `channel_links`（ETF↔联接 / 指数↔ETF） |

由 `data-strategy.md` §4.3.3 推导出的**刷新侧两条硬规则**：

1. **全市场单次调用 → 可以全量**。例：`fund_scale` 用 **1 次**请求换 6,976 只基金规模；若改逐只则需 6,976 次，量级高 3 个数量级。
2. **逐只调用 → 必须按目标池限量 + 设硬上限**。例：`fund_position` 只跑核心池，硬上限 500 只。
   `__full__` 与空 targets 对逐只类 job 一律表示「**无受限目标池**」→ **显式跳过，禁止退化为全库**（原 `fund_meta_job` 正是在此出错，见 #1403）。

## 4. 刷新清单

「实测最后成功」取自 `sync_logs.started_at`（**该列只反映最后一次启动，不代表成功**，故单列「成功/次数」）。

| 数据项 | 层 | job | 建议频率 | 实测最后启动 | 成功/次数 | 状态 |
|--------|----|-----|---------|-------------|----------|------|
| 基金名录 `funds` | L3 | `fund_list` | 每日 | 2026-05-31 | 23/25 | ⏸ 停摆 |
| 净值 `daily_worth` | L3 | `fund_nav` | 每日 | 2026-08-14 | 10/16 | ⏸ 停摆 28 天 |
| 货基万份收益 `money_fund_daily_worth` | L3 | `fund_nav` | 每日 | 2026-08-14 | 10/16 | ⏸ 数据止于 08-16 |
| 行情 `price_history` | L3 | `price_history` | 每日 | 2026-05-31 | 11/13 | ⏸ 停摆 3.5 个月 |
| 股票名录 `securities` | L3 | `stock_list` | 每日 | 2026-05-31 | 25/25 | ⏸ 停摆 |
| 基金详情（全称 / 基准 / 成立日） | L3 | `fund_detail_enrich` | 每周 | 2026-09-11 | 24/24 | ✅ 手动触发 |
| 基金规模 / 份额 | L3 | `fund_scale` | 每周 | 无记录 | — | 🆕 本 PR 新建 |
| 近似股票仓位 | L3 | `fund_position` | 每周 | 无记录 | — | 🆕 本 PR 新建 |
| 基金经理 | L3 | `fund_manager` | 每季 | 2026-09-08 | 2/4 | ⚠️ 有失败 |
| 基金公司主数据 | L3 | `amac_institution` | 每季 | 2026-08-24 | 4/4 | ⚠️ 稀疏 |
| 指数名录 / 成分 / 日线 | L3 | `index_catalog` / `index_constituents` / `index_daily` | 日 / 季 / 日 | 09-11 / 09-08 / 09-09 | 各 1~2 次 | ⚠️ 稀疏 |
| 探市 20 资产快照 | L3 | `market_snapshot` | 每日 08:00 | 待首次跑 | — | 🆕 #1460 方案 B 新建（15 行/天，见 `market-explorer.md` §7） |
| 温度指标 | L3 | `temperature` | 每日 | 2026-08-02 | 25/26 | ⏸ |
| 跨渠道关联 | L4 | `channel_link` | 每月 | 2026-09-11 | 1/1 | ✅ |
| 资产快照 | L2 | `asset_snapshot` | 每日 | 无记录 | — | ❓ 日志盲区（#1402 前抛错不落日志） |
| 基金类型 | L3 | `fund_type` | 每月 | 无记录 | — | ❓ 同上 |

> 「无记录」不等于「没跑过」——在 #1402 修好 `orchestrator` 异常路径落日志之前，**抛错时全链路无日志**，故 2026-09-11 之前的失败无法从 `sync_logs` 回溯。

## 5. CI 调度现状（2026-09-11 实测）

| 项 | 实测 |
|----|------|
| workflow | `.github/workflows/daily-snapshot.yml` |
| 触发 | `schedule: cron '0 17 * * *'`（UTC 17:00 = 北京次日 01:00）+ `workflow_dispatch` |
| 执行内容 | `pdm run scheduler`（复用 `DataSyncOrchestrator.run_all_jobs`） |
| 所在分支 | `main`（**长期落后 `dev`**） |
| 最近 7 次 | 2026-09-04 ~ 09-10 **全部 failure** |
| 失败步骤 | `pdm run scheduler`，**耗时 <1 秒**——启动即崩，不是网络 / 限流问题 |
| 真因 | `DATABASE_URL` / `SUPABASE_DATABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` / `APP_ENV` **secrets 均为空** → `create_engine('')` → `sqlalchemy.exc.ArgumentError: Could not parse SQLAlchemy URL from given URL string` |
| 失败告警 | **无**（workflow 注释写「可接 Actions 失败通知」，未配置） |

**诊断命令**（换 `<run_id>` 即可复现）：

```bash
gh api repos/imoyao/fundmate/actions/workflows/daily-snapshot.yml/runs --jq '.workflow_runs[] | "\(.created_at) \(.event) \(.conclusion)"'
gh run view <run_id> --log-failed
```

> **重要区分**：**部署侧**设计上不引入常驻调度器（由 CI schedule / 系统 cron 外部触发），
> 故「服务器上没有调度进程」是**预期行为**，不是缺陷；真正的问题是**外部触发器存在但连接不到库**——即上表中的 secrets 缺口。
> 而**本机**长期没有触发器（CI 跑的是生产库，改不到本机 SQLite），这一环已由 §5.2 补上（2026-09-13）。

### 5.1 2026-09-12 修复（#1434）

workflow 已按如下三处改（定义仍在 `main`，因为 `schedule` 只认默认分支）：

| 项 | 修复 |
|----|------|
| 调度分支 | `actions/checkout` 显式 `ref: ${{ env.SCHEDULER_REF }}`（默认 `dev`）→ **实际执行 dev 代码**，避开 main 的旧代码 |
| 失败告警 | job 失败时用 `actions/github-script` **自动开/更新一个 tracking issue**（`permissions: issues: write`） |
| secrets 预检 | 新增「校验必需 secrets」步骤：缺失即 `exit 1` 并 `::error` 列出缺失项 —— 不再出现「secret 展开为空串 → `create_engine('')` → ArgumentError、真因不可见」 |

**仍缺、需人工配值的 secrets**（`gh secret list` 实测）：

- 缺失：`APP_ENV`、`DATABASE_URL`、`SUPABASE_DATABASE_URL`、`SUPABASE_SERVICE_ROLE_KEY`
- 已有：`SUPABASE_URL`、`SUPABASE_ANON_KEY`

> 注意 `APP_ENV` 决定选哪套引擎：`production` → market 域走 `TURSO_DATABASE_URL`（回退 `DATABASE_URL`），
> user 域走 `SUPABASE_DATABASE_URL`（见 `app/core/db_factory.py:169-215`）。本机 `backend/.env` 内已有这些键，
> 但**是否为生产值需人工确认**。

### 5.2 2026-09-13 新增：本机常驻调度（#1467）

上表的根因是**「本机库没有任何触发器」**（CI 通道跑的是生产库），于是本机页面上看到的
净值 / 温度永远是陈旧的。#1467 补上本机这一环：应用启动时起**进程内 APScheduler**
（`app/services/daily_scheduler.py`），按 cron 跑三项：

| job | 触发（北京） | 交易日口径 | 对应第 4 节的数据项 |
|-----|-------------|-----------|-------------------|
| `temperature` | 20:00 | `cn`（A 股休市跳过） | 温度指标 |
| `fund_nav` | 21:30 | `cn`（A 股休市跳过） | 净值 `daily_worth` / 货基万份收益 |
| `market_snapshot` | 08:00 | `none`（**7×24，A 股假期照常跑**） | 探市 20 资产快照（#1460 方案 B） |

- 开关 `SCHEDULER_ENABLED`（`backend/.env.example` 默认开，代码默认关）；非开盘日跳过；
  应用启动后延迟补跑「当天已过触发时刻却没成功」的任务；`data/daily_scheduler.lock`
  单实例锁保证同机只跑一份。
- **按任务交易日口径**：`DailyJobSpec.calendar` 取 `cn` / `none`。探市资产的成分含美股 /
  商品 / 汇率，「A 股休市」≠「全球休市」，按全局布尔跳过会让这些卡片在国庆**停更一周**，
  故 `market_snapshot` 标 `none`；补跑判定同样逐任务进行，无全局早退。
- **与 CI 通道的分工**：本机通道更新本机 SQLite（开发 / 自用），CI 通道更新生产库
  （Turso / Supabase），两者是不同库，不冲突、也不互为替代。
- 本机通道**仍不含** `asset_snapshot`（资产快照）；需要的话在 `_JOB_TEMPLATES` 追加一行。
- 查状态：`pdm run invoke sched.status`。详见 `docs/dev/scheduler-tasks.md`。

> 仍**未被任何通道覆盖**的数据项：`price_history`（行情）、`fund_detail_enrich`、
> `fund_scale`、`idx` 系列等——本机仍要手动 `pdm run invoke grab.job <name>`。

## 6. 缺口与待办

| # | 缺口 | 影响 | 去向 |
|---|------|------|------|
| 1 | `daily-snapshot` 所需 secrets 为空 | 每日调度 100% 失败，净值 / 快照停更 | **代码侧已加预检（§5.1）；仍需人工配值** |
| 2 | 调度无失败告警 | 连续 7 天全红无人知晓 | ✅ 已修（§5.1，自动开/更新 issue） |
| 3 | 调度跑 `main`（落后 `dev`） | 即使 secrets 配好，跑的也是旧代码 | ✅ 已修（§5.1，checkout `ref: dev`） |
| 4 | `fund_nav` / `price_history` 已停摆 | 净值止于 08-14、行情止于 05-31 | 净值随 #1 恢复；本机另由 §5.2 覆盖 |
| 5 | 线上 SaaS 多库分层（热 / 温 / 冷） | 单库撑不起全量历史 | 另开 issue，不在本地范围 |
| 6 | `funds` 7 列中 3 列的源缺失 / 未接入 | `risk_level` 等无数据可填 | 见 `tech-debt.md` §16.2 第 5 条 |
| 7 | 本机库无触发器 → 本机页面数据陈旧 | 本地看到的净值 / 温度长期不更新 | ✅ 已修（§5.2；覆盖 `temperature` / `fund_nav` / `market_snapshot`） |
| 8 | `execution_plan` 漏 5 个已注册 job | `run_all_jobs` 实际只跑 16 个，`temperature` / `convertible_bond` / `index_valuation` / `channel_link` / `amac_institution` 从未被编排器批量调度 | ✅ 已修（2026-09-13，#1460 顺带；补 `None` 目标池 + 新增「注册集 = 计划集」双向断言测试） |
| 9 | `AmacInstitutionJob` 的 `_pre_run` / `_post_run` 钩子从不被调用 | 基类 `SyncJob.run()` 未调用这两个钩子，该 job 的「标记失效机构」逻辑永不执行 | ⬜ **另开 issue**（超 #1460 范围，属独立缺陷） |
| 10 | 探市汇率卡曾长期展示 2023 年数据（F6） | 美元指数 / 离岸人民币的「当日涨跌」是 2023 年的 | ✅ 已修（2026-09-13；根因是 `currency_boc_sina` 默认区间被上游硬编码，显式传 `start_date`/`end_date` 即可） |
| 11 | 并发取数会 abort 整个进程（V8 / py_mini_racer） | akshare 有 **40 个模块**用 py_mini_racer（探市 14 资产里 11 个），每次调用新建 V8 isolate，`_FETCH_WORKERS=6` 并发首次创建触发 `FATAL`；**C++ abort 抓不住，Web 服务 / 调度器一起没** | ✅ 已修（2026-09-13；`app/core/v8_guard.py` 守卫挂在全仓唯一收口点 `get_akshare()` 上 → 结构性免疫，见 `decisions.md` D24） |
| 12 | 周末汇率卡显示 `+0.00%` | 源在非工作日追加「顺延行」（值同前一日、中间价 NaN），当日涨跌被算成 0，掩盖周五真实变动；2 张卡同源同参故同时为 0 | ⬜ **待产品口径决策**（剔除顺延行 / 改用最近有效观测日 / 接受现状），见 `market-snapshot-persist-plan-2026-09-13.md` §8.1 |

## 7. 维护约定

- 新增 / 修改 job、调整调度频率后，**必须同步更新第 4 节**（否则本表立刻腐烂）。
- 调整**本机**调度（任务清单 / 触发时刻 / 开关）后，同步更新 §5.2 与
  `docs/dev/scheduler-tasks.md`，并更新文首「最后更新」日期。
- 每次复核本表，先重跑第 5 节的诊断命令刷新「实测现状」列，并更新文首「最后更新」日期。
- 「建议频率」是产品需求口径；实际能否达成取决于第 6 节缺口的关闭情况。

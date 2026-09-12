---
title: 定时任务处理
permalink: /dev/scheduler-tasks
---

> 本文有两个调度通道，**按运行环境二选一或并用**：
>
> | 通道 | 宿主 | 适用 | 章节 |
> |------|------|------|------|
> | 本机常驻（进程内 APScheduler） | 你的 Windows 机器 | 本地开发/自用：打开应用即自动更新 | [§本机常驻](#本机常驻每日数据抓取1467) |
> | 外部触发（CI / 系统 cron） | CI runner / 服务器 | 生产：无常驻进程 | [§外部触发](#每日定时调度1182-已落地) |

## 本机常驻每日数据抓取（#1467）

**解决什么**：本机没有常驻定时器时，「外部触发」通道在本机根本不生效（实测 CI
daily-snapshot 因 secrets 缺失连续 7 天全红，本地库净值止于 2026-08-14、温度止于
2026-08-02）。本节补上「本机常驻」这一环：**应用一起来就在进程内按 cron 更新数据**，
不需要任何外部定时器。

### 两种起法（同机只会有一个生效）

| 方式 | 命令 / 开关 | 说明 |
|------|------------|------|
| 应用内（默认） | `.env` 置 `SCHEDULER_ENABLED=1` | 运行 `dev.cmd` / `flask run --debug` 时随应用启动，零额外操作 |
| 独立守护进程 | `pdm run scheduler-daemon` | 后端不跑也想每天更新时用；`--force` 可忽略开关 |

> 单实例锁 `backend/data/daily_scheduler.lock` 保证同一台机器只有一份在跑：先到先得，
> 后者只会在日志里说明一句然后放弃。进程退出（含崩溃）由内核自动释放，无需人工清理。

### 每日任务

| job | 触发（北京时间） | 内容 |
|-----|-----------------|------|
| `temperature` | 20:00 | 温度计：集思录中位 PB / 韭圈儿 / 行业拥挤度 / 乖离率，即**温度计页面**的数据 |
| `fund_nav` | 21:30 | **自选 + 持仓**的基金净值当日增量（目标池由 `orchestrator.resolve_targets()` 现取） |

- **非开盘日不抓**：周末 / 法定节假日 / 调休补班周末一律跳过（口径唯一来自
  `app/core/trading_calendar.py`）——非交易日没有新数据，空跑只会白送请求 + 留下失败审计。
- **启动补跑**：应用启动后延迟 180s 检查「当天已过触发时刻、却还没有成功记录」的任务并补跑。
  早上 9 点启动不会抢跑（那时数据还没发布），晚上到家开机则能把当天漏掉的补上。
- **抓取礼仪**：每个任务开工前做随机延迟，窗口复用 `SYNC_JITTER_SECONDS`（#1400）。
- **扩任务**：想再加一项（如 `asset_snapshot`，纯本地计算无外部数据源、是前端「每日收益」的
  数据源），在 `app/services/daily_scheduler.py` 的 `_JOB_TEMPLATES` 加一行即可，
  配置项会自动出现在 `--status` 里。

### 配置（`backend/.env`，全部可选）

```ini
SCHEDULER_ENABLED=1                    # 总开关（模板 .env.example 已默认打开）
# SCHEDULER_TIMEZONE=Asia/Shanghai
# SCHEDULER_TEMPERATURE_CRON=0 20 * * *
# SCHEDULER_NAV_CRON=30 21 * * *
# SCHEDULER_SKIP_NON_TRADING_DAY=true  # 休市不抓
# SCHEDULER_RUN_ON_START=true          # 启动补跑
# SCHEDULER_STARTUP_DELAY_SECONDS=180
# SCHEDULER_TEMPERATURE_ENABLED=true
# SCHEDULER_NAV_ENABLED=true
```

### 不会启动的场景（都是刻意的）

| 场景 | 原因 |
|------|------|
| `SCHEDULER_ENABLED` 未打开 | 显式开关，默认关（模板文件里设为开） |
| pytest 进程 | `tests/conftest.py` 每个用例都调 `create_app()`，否则测试会真的发网络请求 |
| `CI=true` | CI 的更新由 `daily-snapshot` workflow 负责，不该重复 |
| Flask 重载**父**进程 | `flask run --debug` 父子两进程都会执行 `create_app()`；让子进程持有，
才能「改代码重载即生效」（父进程模块永远停在启动那一刻） |

### 排查

```bash
pdm run invoke sched.status     # 或 pdm run scheduler --status（只读）
```

输出包含：开关、时区、各任务 cron 与今日触发时刻、**上次成功时间**、单实例锁是否被占用。
日志检索关键字：`[每日调度]`。

### 实现位置

- 调度器：`app/services/daily_scheduler.py`（配置 / 进程判定 / 交易日 / 补跑 / 单实例锁）
- 应用接线：`app/main.py` 的 `create_app()` → `start_daily_scheduler(debug=app.debug)`
- 守护进程：`app/tools/scheduler_daemon.py`（`pdm run scheduler-daemon`）
- 文件锁：`app/core/file_lock.py`（从 orchestrator 抽出，供调度器与编排器共用）
- 测试：`tests/services/test_local_daily_scheduler.py`（全离线，替身编排器）

---

## 每日定时调度（#1182 已落地）

资产快照与净值同步由**每日调度器**自动执行，无需用户打开页面。调度与计算解耦：
外部定时器只「喊一声」，`DataSyncOrchestrator` 在部署侧（或 CI runner）跑重活。

### 架构

- **计算层**：`DataSyncOrchestrator.run_all_jobs`（`app/services/sync/orchestrator.py`）
  按依赖顺序跑全部 SyncJob，**末尾**执行 `asset_snapshot` 落账，确保前面的净值/行情已刷新。
- **入口**：`app/tools/scheduler.py`（`pdm run scheduler`），由外部定时器每日调用；
  支持 `pdm run scheduler --job <name>`（单 job）与 `pdm run scheduler --full`（全量）。
- **触发器（外部，依赖外部定时器）**：
  - GitHub Actions：`.github/workflows/daily-snapshot.yml`，
    `cron: '0 17 * * *'`（UTC，＝北京次日凌晨 01:00），另提供 `workflow_dispatch` 手动触发。
  - 备选：SCF 定时器 / 系统 cron 在部署服务器执行 `pdm run scheduler`（详见 workflow 注释）。

> 注意：本通道跑的是**全量增量同步**（含 `asset_snapshot` 资产快照落账）；
> 上节的本机通道只跑用户最关心的两项（`temperature` / `fund_nav`），不含资产快照。

### 每日更新的信息

- [x] 基金最新净值（`fund_nav` job，增量同步最近 N 天）
- [x] 基金组合配置 / 类型 / 经理等元数据（`fund_list` / `fund_detail_enrich` / `fund_type` / `fund_manager`）
- [x] 每日账户更新（盈利情况）：`asset_snapshot` job 落 `asset_snapshots` 表
      （家庭/账户两级，含货基每日收益 `money_fund_income_cents`，#863 P1-5）

### 季度更新（规划中）

- [ ] 持仓信息
- [ ] 打分信息

### 可观测性

- 单 job 失败不中断整体（`Orchestrator._execute_job` 捕获并继续下一个 job）。
- 每个 job 结果写入 `SyncLog`（`Orchestrator._save_sync_log`），可在库内追溯。
- 未捕获异常以退出码 1 结束进程 → workflow 标红，可接 Actions 失败通知。

### 幂等

- `asset_snapshot` 复用 `summary_service.write_asset_snapshot`（幂等 upsert）；
  `fund_nav` 写入前按 `(fund_code, date)` 去重。同一天重复执行不产生重复快照。

---
title: 定时任务处理
permalink: /dev/scheduler-tasks
---
## 每日定时调度（#1182 已落地）

资产快照与净值同步由**每日调度器**自动执行，无需用户打开页面。调度与计算解耦：
外部定时器只「喊一声」，`DataSyncOrchestrator` 在部署侧（或 CI runner）跑重活。

### 架构

- **计算层**：`DataSyncOrchestrator.run_all_jobs`（`app/services/sync/orchestrator.py`）
  按依赖顺序跑全部 SyncJob，**末尾**执行 `asset_snapshot` 落账，确保前面的净值/行情已刷新。
- **入口**：`tools/scheduler.py`（`pdm run scheduler`），由外部定时器每日调用；
  支持 `pdm run scheduler --job <name>`（单 job）与 `pdm run scheduler --full`（全量）。
- **触发器（外部，无常驻进程）**：
  - GitHub Actions：`.github/workflows/daily-snapshot.yml`，
    `cron: '0 17 * * *'`（UTC，＝北京次日凌晨 01:00），另提供 `workflow_dispatch` 手动触发。
  - 备选：SCF 定时器 / 系统 cron 在部署服务器执行 `pdm run scheduler`（详见 workflow 注释）。

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

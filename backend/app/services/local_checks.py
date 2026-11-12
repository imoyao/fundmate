# -*- coding: utf-8 -*-
"""不产生业务数据的**本地巡检**通道（#3078）。

## 为什么需要一条新通道

`daily_scheduler._JOB_TEMPLATES` 里每一项都是编排器（`DataSyncOrchestrator.jobs`）里的
`SyncJob`，准入判据是「数据日变化 + 用户直接可见」。健康巡检两条都不满足：它不改业务
数据、结论也不出现在任何页面上。硬塞进去要造一个 `_fetch_data` / `_validate_data` /
`_deduplicate` / `_save_data` 四条空实现的假 job——那比没有调度更糟：一个「看起来在跑」
的 job 会让人以为这道防线在。

## 这条通道允许什么（三条同时满足才可登记）

1. **零外部请求**：纯本机数据库 / 文件，不碰任何上游数据源；
2. **只读业务表**：唯一的写是 `sync_logs` 自己的审计行；
3. **判定口径已存在**：规则在别处（如 `cold_set_guard`）已写清并有判据，这里只负责「让它
   按时跑起来」，不在这里新发明规则。

「想让它定期跑」本身**不是**理由——否则任何检查都能借这条路挤进进程内调度。

## 两条入口，同一份到期判据

本仓有两条调度通道，巡检必须**两条都能到**，否则修一半：

- 本机常驻（`SCHEDULER_ENABLED=1` / `pdm run scheduler-daemon`）→ `register_checks` 把它
  注册进 APScheduler；
- 部署侧（GitHub Actions `daily-snapshot.yml` 的 cron）→ 跑的是 `pdm run scheduler` 这个
  **一次性**进程，只会 `orch.run_all_jobs()`，从不启动 APScheduler ⇒ 巡检在那条通道上不会
  被注册。故 `app/tools/scheduler.py` 在同步跑完后调 `run_due_checks()`（#3081）。

两条入口共用 `due_checks` 的「距上次判定 ≥ 6 天」判据，所以既不会重复跑也不会互相漏。

清单写成模块级常量而非纯配置读取：**新增一项必须同时改
`backend/tests/services/test_local_checks.py` 的白名单断言**，那一步就是 review 会看到的
闸门（写进文档的规则会被绕开，需要改测试才能通过的规则不会）。

## 为什么巡检自己落 sync_logs，而不复用编排器审计

编排器落 `stats` 用 `str(dict)`（Python repr，单引号），而 `cold_set_guard.last_guard_stats`
用 `json.loads` 读——走编排器会让「上次基线」**永远读不回来**，判定永远停在「首次巡检」：
不膨胀、不报错、日志全绿。所以巡检自己写 json（`cold_set_guard.record`），并在
`test_local_checks.py` 里钉住「一次落库能被读回」的闭环。
"""

import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from loguru import logger

from app.services import cold_set_guard

ENV_COLD_SET_GUARD_ENABLED = 'SCHEDULER_COLD_SET_GUARD_ENABLED'
ENV_COLD_SET_GUARD_CRON = 'SCHEDULER_COLD_SET_GUARD_CRON'
# 周一 04:10：现有日跑最晚是 23:45 的 asset_snapshot，凌晨整段空着；错开整点是为了不与
# 机器上其它定时器撞在同一秒。**周频**而非日频：膨胀来自回填写入（P0-2 按需取是 30 分钟
# 防抖的慢速路径），从不来自日更，日跑换不到新信息（#3078 的判据）。
DEFAULT_COLD_SET_GUARD_CRON = '10 4 * * mon'


@dataclass(frozen=True)
class LocalCheckSpec:
    """一条本地巡检。

    Attributes:
        job_name: 写进 `sync_logs.job_name` 的名字（必与 `cold_set_guard.GUARD_JOB_NAME`
            一致，否则基线读不回来——由 `test_local_checks` 对账）。
        cron: 五段式 cron，按 `DailySchedulerConfig.timezone` 解释。
        runner: 无参可调用对象，返回 `{'job_name', 'status', 'stats'}` 形态（与
            `run_sync_job` 同构，便于调度器用同一套日志口径）。
        description: 人可读说明，进日志与 `--status`。
    """

    job_name: str
    cron: str
    runner: Callable[[], Dict[str, Any]]
    description: str


def _run_cold_set_bloat_guard() -> Dict[str, Any]:
    """跑一次冷集膨胀巡检并落库。

    全部依赖惰性 import：本模块在 `daily_scheduler` 顶层被引入，应用启动路径不应因此
    多加载数据层（同 `daily_scheduler` 模块头约束）。
    """
    from app.core.database import get_session
    from app.services import cold_set_check

    db = get_session()
    try:
        outcome = cold_set_check.run_check_and_record(db)
    finally:
        db.close()
    report = outcome.report

    # status 用 `bloated` 而非 `success`：调度器按「非 success 打 warning」处理，
    # 一跑就膨胀是必须被看见的信号，但它不是执行失败（job 本身跑通了）。
    return {
        'job_name': cold_set_guard.GUARD_JOB_NAME,
        'status': 'bloated' if report.bloated else 'success',
        'stats': report.to_stats(),
    }


def _enabled(raw: Optional[str], default: bool) -> bool:
    """解析开关型环境变量：空/未设 → default；1/true/yes/on → True。"""
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def build_checks(env: Optional[Mapping[str, str]] = None) -> Tuple[LocalCheckSpec, ...]:
    """按环境变量构造本次启用的巡检清单（缺省全开）。"""
    source: Mapping[str, str] = os.environ if env is None else env
    checks = []
    if _enabled(source.get(ENV_COLD_SET_GUARD_ENABLED), True):
        checks.append(
            LocalCheckSpec(
                job_name=cold_set_guard.GUARD_JOB_NAME,
                cron=(source.get(ENV_COLD_SET_GUARD_CRON) or DEFAULT_COLD_SET_GUARD_CRON).strip(),
                runner=_run_cold_set_bloat_guard,
                description='冷集膨胀巡检（周频，纯本地只读）',
            )
        )
    return tuple(checks)


def last_run(db, job_name: str):
    """该巡检最近一次运行的审计行（**任何 status 都算**，没跑过返回 None）。

    不能用 `SyncLog.get_last_sync_time`：它只认 `status == 'success'`，而巡检落库的 status
    是 `ok` / `bloated`（后者恰恰是最该被看见的那一半），用它会把「跑过且判了膨胀」和
    「从未跑过」显示成同一句话——那正是 #3078 要防的「挂了和没挂看起来一样」。
    """
    from sqlalchemy import desc

    from app.models.sync_log import SyncLog

    return db.query(SyncLog).filter(SyncLog.job_name == job_name).order_by(desc(SyncLog.started_at)).first()


def last_run_at(db, job_name: str):
    """最近一次运行的时间（口径同 `last_run`）。"""
    row = last_run(db, job_name)
    return row.started_at if row else None


# 与 `orchestrator.WEEKLY_JOB_MIN_INTERVAL_DAYS` 同值同理由（CI 起跑有最长约 10 分钟的
# jitter，卡 7 天会让「每周一次」漂成 8 天）。巡检不走编排器那道门控，故在这里单独定义。
MIN_INTERVAL_DAYS = 6
# 「判定已经发生」的状态：`ok` 与 `bloated` 都算。若把 `bloated` 排除在外，下一轮会再记
# 一次基线，`growth` 恒为 0 ⇒ 膨胀永远看不见，那是比假红更贵的失效。
_JUDGED_STATUSES = ('ok', 'bloated')


def due_checks(db, now=None, min_interval_days: int = MIN_INTERVAL_DAYS, checks=None) -> Tuple[LocalCheckSpec, ...]:
    """本轮该跑的巡检（一次性执行路径与 APScheduler 共用这一份到期判据）。

    判据与 `orchestrator._skip_if_recent` 方向一致、口径不同：日跑 job 只认 `success`
    （失败那次不该算「刚跑过」）；巡检认 `ok` / `bloated`——两者都表示**判定已经发生**。
    `error` 与其它未知状态一律视为「没跑成」，按日重试，而不是等满一周。
    """
    from app.core.time_utils import now_shanghai

    now = now or now_shanghai()
    specs = build_checks() if checks is None else checks
    due = []
    for spec in specs:
        row = last_run(db, spec.job_name)
        judged = row is not None and (row.status or '') in _JUDGED_STATUSES
        # 用日期差而非时间差：`started_at` 从 SQLite 读回是 naive 东八区墙钟，直接与
        # aware 的 now 相减会抛 TypeError（同 #1793 的形态）；周频按天判定也够用。
        if not judged or (now.date() - row.started_at.date()).days >= min_interval_days:
            due.append(spec)
    return tuple(due)


def run_due_checks(now=None, env: Optional[Mapping[str, str]] = None) -> list:
    """在**一次性**执行路径里跑掉本轮到期的巡检（`pdm run scheduler`）。

    为什么需要这条入口：部署侧（`daily-snapshot.yml` 的 cron）跑的是 `pdm run scheduler`
    这个一次性进程，它只调 `orch.run_all_jobs()`，**从不启动 APScheduler**——只在
    `daily_scheduler.start()` 里注册的巡检在那条通道上永远不会跑，等于 #3078 的修复只覆盖
    了「本机常驻」一半。两条入口共用 `due_checks`，所以既不会重复跑也不会互相漏。
    """
    from app.core.database import get_session

    db = get_session()
    try:
        specs = due_checks(db, now=now, checks=build_checks(env))
    finally:
        # 先关掉判定用的会话再跑：巡检自己开会话（`get_session`），SQLite 上两个会话
        # 同时持有读事务没有意义，只会给锁等待留口子。
        db.close()

    if not specs:
        logger.info('[本地巡检] 本轮无到期巡检')
        return []
    return [run_local_check(spec) for spec in specs]


def register_checks(scheduler, tzinfo, checks) -> None:
    """把巡检注册进 APScheduler（`id` 即 job_name——撞名会静默顶掉一个日跑 job）。"""
    from apscheduler.triggers.cron import CronTrigger

    for check in checks:
        # 巡检刻意**不看** `skip_non_trading_day`：那条判据问的是「今天有没有新数据」，
        # 而数据膨胀来自回填写入，与交易日无关；周频只有一次机会，跳过就是整周空档。
        scheduler.add_job(
            run_local_check,
            trigger=CronTrigger.from_crontab(check.cron, timezone=tzinfo),
            id=check.job_name,
            name=f'巡检 {check.job_name}（{check.description}）',
            args=[check],
            replace_existing=True,
        )


def describe_checks(db, checks, now: Any) -> list:
    """`--status` 里巡检那几行（「上次巡检多久前」是 #3078 唯一的外部可见性）。"""
    lines = []
    for check in checks:
        last = last_run_at(db, check.job_name)
        # 这里与 `jobs` 分开列：日跑用 `get_last_sync_time`（只认 success）是对的，
        # 巡检的 status 是 `ok` / `bloated`，用同一个读法会恒显示「无记录」。
        age = f'{(now.date() - last.date()).days} 天前' if last else '从未跑过'
        lines.append(f'  · {check.job_name:<24} cron={check.cron:<12} 上次巡检={age}  {check.description}')
    return lines


def run_local_check(spec: LocalCheckSpec) -> Dict[str, Any]:
    """执行一条巡检；异常收敛为结构化结果。

    与 `daily_scheduler.run_sync_job` 同样兜住一切：后台线程里抛出的异常只会变成
    APScheduler 的一行日志，调用方看不到原因。差异是不注入 targets、也不写编排器审计
    （理由见模块 docstring）。
    """
    logger.info(f'[本地巡检] 开始 {spec.job_name}（{spec.description}）')
    try:
        result = spec.runner()
    except Exception as exc:  # noqa: BLE001 - 调度线程必须兜住一切
        logger.exception(f'[本地巡检] {spec.job_name} 执行异常：{exc}')
        return {'job_name': spec.job_name, 'status': 'error', 'error': str(exc)}

    if result.get('status') == 'success':
        logger.info(f'[本地巡检] {spec.job_name} 完成：{result.get("stats")}')
    else:
        logger.warning(f'[本地巡检] {spec.job_name} 需要关注：status={result.get("status")} {result.get("stats")}')
    return result

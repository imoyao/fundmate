# -*- coding: utf-8 -*-
# app/services/daily_scheduler.py
"""本机常驻的「每日数据抓取」调度器（进程内 APScheduler，#1467）。

为什么需要它
    `app/tools/scheduler.py` 是**外部触发**入口：由 CI schedule / 系统 cron 每天喊一次
    `pdm run scheduler`。本机没有常驻定时器时它根本不会自己跑——实测 CI 的
    daily-snapshot 因 secrets 缺失连续 7 天全红（见 `docs/spec/data-refresh-inventory.md`
    §5），本地库因此净值止于 2026-08-14、温度止于 2026-08-02。本模块补上「本机常驻」
    这一环：随 Flask 应用（或独立守护进程）启动，进程内按 cron 触发，不依赖任何外部定时器。

职责边界
    只做**调度**。真正的抓取与落库仍全部走 `DataSyncOrchestrator`，本模块不实现任何
    业务逻辑，也不自己解析「该抓哪些代码」——目标池由 `orchestrator.resolve_targets()`
    统一给出（持仓 + 自选），与外部触发路径完全同源。

硬约束（每条都有事故来源，勿删）
    1. **单实例**：只有拿到 `data/daily_scheduler.lock` 的进程才启动调度。`flask run --debug`
       下**重载父进程与子进程都会执行 create_app()**，没有锁就会各跑一份 → 同一天抓两遍。
       锁在进程退出时由内核释放（见 `app/core/file_lock.py`）。
    2. **不在测试 / CI 进程里启动**：`tests/conftest.py` 的 `app` fixture 每个测试都会调
       `create_app()`，无脑启动会在测试里拉起后台线程与真实网络请求。
    3. **重依赖延迟导入**：应用启动路径不得连带加载 akshare / orchestrator / pandas ——
       编排器只在任务真正触发时才构造（`_build_orchestrator`）。
    4. **不阻塞、不失败**：APScheduler 跑在后台线程；启动补跑也带延迟；任何启动异常都只
       记日志，绝不让「数据更新」这个增强项把应用启动搞挂。

触发时刻（北京时间，均可用环境变量覆盖，见 backend/.env.example）
    - `temperature` 20:00 —— 温度源（集思录中位 PB / 韭圈儿 / 行业拥挤度）盘后即出。
    - `fund_nav`    21:30 —— 场外基金净值通常 19:00~24:00 陆续公布，21:30 可覆盖大头；
      当晚漏掉的由次日增量的「上次成功日 − 1 天」窗口自动补齐（见 `FundNavSyncJob`）。

用法
    - 应用内：`.env` 里置 `SCHEDULER_ENABLED=1`，`create_app()` 自动启动（默认路径）。
    - 独立守护：`pdm run scheduler-daemon`（后端不跑也想更新数据时用）。
    - 查看状态：`pdm run scheduler --status`（只读，不动数据）。
"""

import os
import sys
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo

from loguru import logger

# 必须先导入全部域模型再做任何 DB 操作：否则跨域外键（如 ledgers.portfolio_id →
# portfolios.id）解析失败并抛 NoReferencedTableError —— #1182 的 `pdm run scheduler`
# 曾因此在启动时直接崩掉。本模块会被**不经 Flask 应用工厂**的脚本入口
# （app/tools/scheduler_daemon.py）直接 import，不能指望「蓝图顺带导入所有模型」，
# 故在此集中声明。约定与 tests/conftest.py、app/tools/scheduler.py 一致。
import app.domains.assets.models  # noqa: F401
import app.domains.families.models  # noqa: F401
import app.domains.funds.models  # noqa: F401
import app.domains.indices.models  # noqa: F401
import app.domains.ledgers.models  # noqa: F401
import app.domains.portfolios.models  # noqa: F401
import app.domains.positions.models  # noqa: F401
import app.domains.price_history.models  # noqa: F401
import app.domains.securities.models  # noqa: F401
import app.domains.strategy.models  # noqa: F401
import app.domains.summary.models  # noqa: F401
import app.domains.transactions.models  # noqa: F401
import app.domains.users.models  # noqa: F401
import app.domains.watchlist.models  # noqa: F401
from app.core.database import get_db
from app.core.file_lock import acquire_lock, release_lock
from app.core.jitter import apply_jitter, random_gap, resolve_jitter_seconds
from app.core.time_utils import today_shanghai
from app.core.trading_calendar import is_trading_day
from app.models.sync_log import SyncLog

# ── 环境变量名（集中在此，便于 .env.example 与文档对齐） ──────────────────

ENV_ENABLED = 'SCHEDULER_ENABLED'
ENV_TIMEZONE = 'SCHEDULER_TIMEZONE'
ENV_SKIP_NON_TRADING_DAY = 'SCHEDULER_SKIP_NON_TRADING_DAY'
ENV_RUN_ON_START = 'SCHEDULER_RUN_ON_START'
ENV_STARTUP_DELAY = 'SCHEDULER_STARTUP_DELAY_SECONDS'
ENV_TEMPERATURE_ENABLED = 'SCHEDULER_TEMPERATURE_ENABLED'
ENV_TEMPERATURE_CRON = 'SCHEDULER_TEMPERATURE_CRON'
ENV_NAV_ENABLED = 'SCHEDULER_NAV_ENABLED'
ENV_NAV_CRON = 'SCHEDULER_NAV_CRON'

DEFAULT_TIMEZONE = 'Asia/Shanghai'
# 温度计：集思录中位 PB / 韭圈儿 / 行业拥挤度盘后即出
DEFAULT_TEMPERATURE_CRON = '0 20 * * *'
# 基金净值：场外净值 19:00~24:00 陆续公布
DEFAULT_NAV_CRON = '30 21 * * *'

# backend/ 目录（app/services/daily_scheduler.py → parents[2]）
BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_LOCK_FILE = BACKEND_DIR / 'data' / 'daily_scheduler.lock'

# 启动补跑的默认延迟：给应用启动/重载让路，避免与启动期 IO 抢资源
DEFAULT_STARTUP_DELAY_SECONDS = 180
# 错过触发时刻的宽限：笔记本合盖过夜、早上唤醒时仍补上当天那一次；超过则跳过（下一天再来）
MISFIRE_GRACE_SECONDS = 6 * 3600


# ── 配置 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DailyJobSpec:
    """一个每日任务。

    Attributes:
        job_name: 编排器（DataSyncOrchestrator.jobs）里的 job 名。
        cron: 五段式 cron（分 时 日 月 周），按 `DailySchedulerConfig.timezone` 解释。
        target_kind: 目标代码类型，`None` 表示该 job 不需要目标池（如 temperature）；
            `'fund'` / `'stock'` 表示目标由 `orchestrator.resolve_targets()` 现取
            （持仓 + 自选）——**绝不能省**：`FundNavSyncJob` 拿到空 targets 会直接
            跳过（`_allow_empty_data=True`），等于空跑还不报错。
        description: 人可读说明，进日志与 `--status`。
    """

    job_name: str
    cron: str
    target_kind: Optional[str]
    description: str


@dataclass(frozen=True)
class DailySchedulerConfig:
    """调度器配置（全部来自环境变量，便于在 `.env` 里逐项调整）。"""

    enabled: bool
    timezone: str
    jobs: Tuple[DailyJobSpec, ...]
    jitter_seconds: int
    skip_non_trading_day: bool
    run_on_start: bool
    startup_delay_seconds: int
    lock_file: Path = DEFAULT_LOCK_FILE

    def job_names(self) -> List[str]:
        return [spec.job_name for spec in self.jobs]


# job 名 → (开关环境变量, cron 环境变量, 默认 cron, 目标类型, 说明)
_JOB_TEMPLATES: Tuple[Tuple[str, str, str, str, Optional[str], str], ...] = (
    (
        'temperature',
        ENV_TEMPERATURE_ENABLED,
        ENV_TEMPERATURE_CRON,
        DEFAULT_TEMPERATURE_CRON,
        None,
        '温度计（集思录 / 韭圈儿 / 行业拥挤度 / 乖离率）',
    ),
    (
        'fund_nav',
        ENV_NAV_ENABLED,
        ENV_NAV_CRON,
        DEFAULT_NAV_CRON,
        'fund',
        '自选 + 持仓的基金净值（当日增量）',
    ),
)


def _truthy(raw: Optional[str], default: bool) -> bool:
    """解析「开关型」环境变量：空/未设 → default；1/true/yes/on（大小写不敏感）→ True。"""
    if raw is None or raw.strip() == '':
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def _int_or(raw: Optional[str], default: int) -> int:
    """解析整数环境变量；无法解析时回退默认值（不因配置笔误让调度停摆）。"""
    if raw is None or raw.strip() == '':
        return default
    try:
        return int(float(raw.strip()))
    except (TypeError, ValueError):
        logger.warning(f'[每日调度] 环境变量值 {raw!r} 不是整数，回退默认 {default}')
        return default


def load_config(env: Optional[Mapping[str, str]] = None) -> DailySchedulerConfig:
    """从环境变量装载调度配置。

    Args:
        env: 环境变量映射，默认取 `os.environ`（测试可注入 dict）。

    注意：抖动窗口固定复用 `SYNC_JITTER_SECONDS`（`app.core.jitter`），
    不另立一套「抓取礼仪」配置——外部 cron 与本机调度面对的是同一批数据源。
    """
    source: Mapping[str, str] = os.environ if env is None else env

    jobs: List[DailyJobSpec] = []
    for job_name, enabled_env, cron_env, default_cron, target_kind, description in _JOB_TEMPLATES:
        if not _truthy(source.get(enabled_env), True):
            continue
        jobs.append(
            DailyJobSpec(
                job_name=job_name,
                cron=(source.get(cron_env) or default_cron).strip(),
                target_kind=target_kind,
                description=description,
            )
        )

    return DailySchedulerConfig(
        enabled=_truthy(source.get(ENV_ENABLED), False),
        timezone=(source.get(ENV_TIMEZONE) or DEFAULT_TIMEZONE).strip(),
        jobs=tuple(jobs),
        jitter_seconds=resolve_jitter_seconds(),
        skip_non_trading_day=_truthy(source.get(ENV_SKIP_NON_TRADING_DAY), True),
        run_on_start=_truthy(source.get(ENV_RUN_ON_START), True),
        startup_delay_seconds=_int_or(source.get(ENV_STARTUP_DELAY), DEFAULT_STARTUP_DELAY_SECONDS),
    )


# ── 进程判定（决定「这个进程该不该起调度器」） ──────────────────────────


def _in_test_process() -> bool:
    """当前是否 pytest 进程（含 fixture 阶段）。

    `tests/conftest.py` 的 `app` fixture 每个测试都调 `create_app()`；若在那里启动
    调度器，会拉起后台线程并可能在测试中发真实网络请求。`PYTEST_CURRENT_TEST` 只在
    测试运行期存在，故同时看 `pytest` 是否已进 `sys.modules`（覆盖 import 阶段）。
    """
    return 'pytest' in sys.modules or 'PYTEST_CURRENT_TEST' in os.environ


def _in_ci() -> bool:
    """当前是否 CI 环境（GitHub Actions 会设 `CI=true`）。

    CI 的每日更新由 `.github/workflows/daily-snapshot.yml` 走外部触发，
    既不该、也不需要进程内再起一份。
    """
    return _truthy(os.getenv('CI'), False)


def _is_reloader_parent(debug: Optional[bool] = None) -> bool:
    """当前是否 Werkzeug 重载的**父**进程。

    `flask run --debug` 会先在执行进程里 import 应用（父），再以
    `WERKZEUG_RUN_MAIN=true` 重新 exec 出真正干活的子进程——两者都会执行 `create_app()`。
    父进程不处理请求、模块永远停在启动那一刻（改代码不会重载），所以让**子进程**持有
    调度器：改了调度/同步代码后重载即生效。

    识别不到时**不做任何假设**（宁可父进程起）：单实例锁才是最终保证，这里只是优化。
    """
    if os.getenv('WERKZEUG_RUN_MAIN') == 'true':
        return False
    if os.getenv('FLASK_RUN_FROM_CLI') != 'true':
        return False
    return debug if debug is not None else _truthy(os.getenv('FLASK_DEBUG'), False)


def should_start(config: DailySchedulerConfig, debug: Optional[bool] = None) -> bool:
    """是否应在当前进程启动调度器（每条拒绝都给出可读原因）。"""
    if not config.enabled:
        logger.debug(f'[每日调度] {ENV_ENABLED} 未开启，跳过启动')
        return False
    if _in_test_process():
        logger.debug('[每日调度] 测试进程，跳过启动')
        return False
    if _in_ci():
        logger.info('[每日调度] CI 环境（CI=true），跳过启动（CI 由 daily-snapshot workflow 负责）')
        return False
    if _is_reloader_parent(debug):
        logger.info('[每日调度] 当前是 Flask 重载父进程，跳过启动（由重载后的子进程持有调度器）')
        return False
    if not config.jobs:
        logger.warning('[每日调度] 没有任何启用的任务（检查 SCHEDULER_*_ENABLED），跳过启动')
        return False
    return True


# ── 时间与交易日 ─────────────────────────────────────────────────────────


def is_rest_day(today: Optional[date] = None) -> bool:
    """今天是否休市（周末 / 法定节假日 / 调休补班周末）。

    口径唯一来自 `app.core.trading_calendar`：非开盘日净值与温度都不会更新，
    按点空跑只会白送一批请求 + 留下失败的 sync_log，故直接跳过。
    """
    return not is_trading_day(today or today_shanghai())


def today_fire_time(cron: str, tzinfo: Any, now: datetime) -> Optional[datetime]:
    """今天该 cron 的触发时刻；今天不触发则返回 None。

    借 APScheduler 的 `CronTrigger` 解析，**不自写 cron 解析器**——保证「判断是否已到点」
    与实际调度用的是同一套语义（含 month/year 字段的边界行为）。
    """
    from apscheduler.triggers.cron import CronTrigger

    trigger = CronTrigger.from_crontab(cron, timezone=tzinfo)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    fire = trigger.get_next_fire_time(None, day_start)
    if fire is None or fire.date() != now.date():
        return None
    return fire


def catch_up_targets(
    config: DailySchedulerConfig,
    now: datetime,
    last_success_dates: Mapping[str, Optional[date]],
) -> List[str]:
    """启动补跑：今天「已过触发时刻、却还没有成功记录」的任务列表。

    以「今天该 cron 的触发时刻是否已过」为界，而不是「今天是否成功过」——否则早上 9 点
    一启动就会抢在数据发布前空跑一遍；而「过了点却还没成功」（机器关机 / 应用没开）
    正是需要补跑的场景，不补就会整天空档。
    """
    tzinfo = ZoneInfo(config.timezone)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tzinfo)
    if config.skip_non_trading_day and is_rest_day(now.date()):
        return []

    due: List[str] = []
    for spec in config.jobs:
        fire = today_fire_time(spec.cron, tzinfo, now)
        if fire is None or now < fire:
            continue
        last_success = last_success_dates.get(spec.job_name)
        if last_success is None or last_success < now.date():
            due.append(spec.job_name)
    return due


# ── 执行 ────────────────────────────────────────────────────────────────


def _build_orchestrator(db):
    """惰性构造编排器。

    两重原因：① 应用启动路径不得加载 akshare（见模块头约束 3）；② 便于测试整体替换，
    避免单测里真的发网络请求。
    """
    from app.services.sync.orchestrator import DataSyncOrchestrator

    return DataSyncOrchestrator(db)


def last_success_date(job_name: str) -> Optional[date]:
    """该 job 最后一次**成功**同步的日期（无记录返回 None）。

    以 `sync_logs` 为准（编排器每跑完一个 job 都会写一行）。SQLite 侧
    `started_at` 存的是东八区墙钟时间的 naive datetime，取 `.date()` 即当地日期。
    """
    with get_db() as db:
        last = SyncLog.get_last_sync_time(db, job_name)
    return last.date() if last else None


def run_sync_job(spec: DailyJobSpec, jitter_seconds: int = 0) -> Dict[str, Any]:
    """跑一个编排器 job（供调度线程与 CLI 调用）。

    独立 DB 会话（`get_db()`），绝不复用任何请求上下文会话。异常在此收敛为结构化结果：
    后台线程里抛出的异常只会变成 APScheduler 的一行日志，调用方看不到失败原因。

    Returns:
        编排器的结果字典；失败时 `status='error'`。
    """
    if jitter_seconds > 0:
        # 抓取礼仪（#1400）：固定时刻触发对数据源是机器人指纹，开工前先随机延迟
        apply_jitter(jitter_seconds, label=f'每日调度 {spec.job_name}')

    try:
        with get_db() as db:
            orchestrator = _build_orchestrator(db)
            targets = None
            if spec.target_kind is not None:
                # 目标池统一由编排器解析（持仓 + 自选），与 `pdm run scheduler` 同源。
                # 空列表交给 job 自行处理：净值类 job 允许空数据，会正常记一条 success。
                targets = orchestrator.resolve_targets().get(spec.target_kind, [])
            return orchestrator.run_job(spec.job_name, targets=targets)
    except Exception as exc:  # noqa: BLE001 - 调度线程必须兜住一切
        logger.exception(f'[每日调度] {spec.job_name} 执行异常：{exc}')
        return {'job_name': spec.job_name, 'status': 'error', 'error': str(exc)}


# ── 调度器 ──────────────────────────────────────────────────────────────


class DailyScheduler:
    """进程内每日调度器（`BackgroundScheduler` 的薄封装）。

    只做三件事：单实例加锁、注册 cron 任务、把执行结果记进日志。状态（`sync_logs`）
    由编排器负责，本类不重复落库。
    """

    def __init__(self, config: DailySchedulerConfig):
        self.config = config
        self._scheduler = None
        self._lock_fd: Optional[int] = None
        self._started = False

    @property
    def running(self) -> bool:
        return bool(self._started and self._scheduler is not None and self._scheduler.running)

    def start(self) -> bool:
        """启动调度器；未拿到单实例锁时返回 False（属正常情况，不算失败）。"""
        if self.running:
            return True
        if not self._acquire_leader_lock():
            return False

        try:
            self._scheduler = self._build_scheduler()
            self._register_jobs(self._scheduler)
            self._scheduler.start()
            self._started = True
        except Exception:
            # 启动失败必须还锁，否则「一次失败」会永久占住单实例名额直到进程退出
            self._release_leader_lock()
            raise

        self._log_plan()
        return True

    def shutdown(self, wait: bool = False) -> None:
        """停止调度器并释放单实例锁。"""
        if self._scheduler is not None:
            try:
                self._scheduler.shutdown(wait=wait)
            except Exception as exc:  # noqa: BLE001 - 关机路径不允许抛
                logger.warning(f'[每日调度] 关闭调度器时出错（已忽略）：{exc}')
        self._scheduler = None
        self._started = False
        self._release_leader_lock()

    # ── 内部 ──

    def _acquire_leader_lock(self) -> bool:
        locked, fd = acquire_lock(self.config.lock_file)
        if not locked:
            logger.info(
                f'[每日调度] {self.config.lock_file.name} 已被其它进程持有，本进程不启动调度器'
                '（同一台机器只跑一份：应用内调度与 `pdm run scheduler-daemon` 二选一即可）'
            )
            return False
        self._lock_fd = fd
        return True

    def _release_leader_lock(self) -> None:
        release_lock(self._lock_fd)
        self._lock_fd = None

    def _build_scheduler(self):
        from apscheduler.schedulers.background import BackgroundScheduler

        return BackgroundScheduler(
            timezone=ZoneInfo(self.config.timezone),
            job_defaults={
                # 同一 job 不并发（净值同步本身也不幂等安全，重复跑纯属浪费请求）
                'max_instances': 1,
                # 错过触发时刻（休眠 / 正好在重启）合并成一次，而不是把错过的每次补跑
                'coalesce': True,
                'misfire_grace_time': MISFIRE_GRACE_SECONDS,
            },
        )

    def _register_jobs(self, scheduler) -> None:
        from apscheduler.triggers.cron import CronTrigger

        tzinfo = ZoneInfo(self.config.timezone)
        for spec in self.config.jobs:
            scheduler.add_job(
                self._run_job,
                trigger=CronTrigger.from_crontab(spec.cron, timezone=tzinfo),
                id=spec.job_name,
                name=f'每日 {spec.job_name}（{spec.description}）',
                args=[spec],
                replace_existing=True,
            )

        if self.config.run_on_start:
            # 启动补跑：应用一起就开始更新（当天已过点却没成功时），而不是干等到明天
            run_date = datetime.now(tzinfo) + timedelta(seconds=self.config.startup_delay_seconds)
            scheduler.add_job(
                self._startup_catch_up,
                trigger='date',
                run_date=run_date,
                id='startup_catch_up',
                name='启动补跑（错过的当日任务）',
                replace_existing=True,
            )

    def _run_job(self, spec: DailyJobSpec) -> None:
        if self.config.skip_non_trading_day and is_rest_day():
            logger.info(f'[每日调度] {spec.job_name} 跳过：今天休市（无新数据可抓）')
            return

        logger.info(f'[每日调度] 开始 {spec.job_name}（{spec.description}）')
        result = run_sync_job(spec, jitter_seconds=self.config.jitter_seconds)
        status = result.get('status')
        if status == 'success':
            logger.info(f'[每日调度] {spec.job_name} 完成：{result.get("stats")}')
        else:
            logger.warning(f'[每日调度] {spec.job_name} 未成功：status={status} {result.get("error") or ""}')

    def _startup_catch_up(self) -> None:
        if self.config.skip_non_trading_day and is_rest_day():
            logger.info('[每日调度] 启动补跑跳过：今天休市')
            return

        now = datetime.now(ZoneInfo(self.config.timezone))
        last_dates = {spec.job_name: last_success_date(spec.job_name) for spec in self.config.jobs}
        due = catch_up_targets(self.config, now, last_dates)
        if not due:
            logger.info('[每日调度] 启动补跑：当日任务均已执行或尚未到点，无需补跑')
            return

        logger.info(f'[每日调度] 启动补跑：{due}（当日已过触发时刻但无成功记录）')
        by_name = {spec.job_name: spec for spec in self.config.jobs}
        for job_name in due:
            self._run_job(by_name[job_name])
            # 两个任务连打不同数据源，之间加随机间隔，避免形成突发请求
            random_gap(label='补跑任务间隔')

    def _log_plan(self) -> None:
        plan = '；'.join(f'{job.id} 下次 {getattr(job, "next_run_time", None)}' for job in self._scheduler.get_jobs())
        logger.info(
            f'[每日调度] 已启动（时区 {self.config.timezone}，抖动窗口 {self.config.jitter_seconds}s，'
            f'休市跳过={self.config.skip_non_trading_day}）：{plan}'
        )


# ── 模块级单例（应用内启动的唯一入口） ──────────────────────────────────

_scheduler: Optional['DailyScheduler'] = None
_scheduler_guard = threading.Lock()


def get_daily_scheduler() -> Optional[DailyScheduler]:
    """取当前进程的调度器实例（未启动返回 None）。"""
    return _scheduler


def start_daily_scheduler(
    config: Optional[DailySchedulerConfig] = None,
    debug: Optional[bool] = None,
) -> Optional[DailyScheduler]:
    """启动进程内每日调度（幂等）。

    Args:
        config: 配置，默认从环境变量装载。
        debug: 调用方的 debug 标记（Flask 传 `app.debug`），用于识别重载父进程；
            传 None 时回退读 `FLASK_DEBUG` 环境变量。

    Returns:
        运行中的调度器实例；未启用 / 不满足启动条件 / 启动失败均返回 None
        ——**调用方无需区分**，这是增强项而非可用性前提。
    """
    global _scheduler
    with _scheduler_guard:
        if _scheduler is not None and _scheduler.running:
            return _scheduler

        try:
            resolved = config or load_config()
            if not should_start(resolved, debug=debug):
                return None
            scheduler = DailyScheduler(resolved)
            if not scheduler.start():
                return None
        except Exception as exc:  # noqa: BLE001 - 调度启动失败绝不阻断应用启动
            logger.exception(f'[每日调度] 启动失败（不影响应用运行）：{exc}')
            return None

        _scheduler = scheduler
        return scheduler


def shutdown_daily_scheduler(wait: bool = False) -> None:
    """停止当前进程的调度器（应用退出时调用；未启动时是 no-op）。"""
    global _scheduler
    with _scheduler_guard:
        if _scheduler is None:
            return
        _scheduler.shutdown(wait=wait)
        _scheduler = None


# ── 运维观测 ────────────────────────────────────────────────────────────


def _is_lock_held(lock_file: Path) -> Optional[bool]:
    """锁文件当前是否被占用（True 占用 / False 空闲 / None 探测失败）。"""
    locked, fd = acquire_lock(lock_file)
    if not locked:
        return True
    release_lock(fd)
    return False


def describe_status(config: Optional[DailySchedulerConfig] = None) -> List[str]:
    """返回人可读的调度状态（`pdm run scheduler --status`）。

    只读：不动数据、不启调度，DB 不可读时降级为提示而不是抛错——「查状态」不应该
    比「跑任务」还脆。
    """
    resolved = config or load_config()
    tzinfo = ZoneInfo(resolved.timezone)
    now = datetime.now(tzinfo)

    held = _is_lock_held(resolved.lock_file)
    lock_state = {True: '运行中（单实例锁被占用）', False: '未运行（单实例锁空闲）', None: '未知（探测失败）'}[held]

    lines = [
        f'开关 {ENV_ENABLED}={resolved.enabled}（测试 / CI 进程会被强制跳过）',
        f'时区 {resolved.timezone}；抖动窗口 {resolved.jitter_seconds}s；'
        f'休市跳过 {resolved.skip_non_trading_day}；启动补跑 {resolved.run_on_start}'
        f'（延迟 {resolved.startup_delay_seconds}s）',
        f'单实例锁 {resolved.lock_file} → {lock_state}',
        f'当前时间 {now:%Y-%m-%d %H:%M:%S}（{"开盘日" if is_trading_day(now.date()) else "休市"}）',
    ]

    try:
        with get_db() as db:
            for spec in resolved.jobs:
                fire = today_fire_time(spec.cron, tzinfo, now)
                last = SyncLog.get_last_sync_time(db, spec.job_name)
                lines.append(
                    f'  · {spec.job_name:<12} cron={spec.cron:<12} '
                    f'今日触发={fire.strftime("%H:%M") if fire else "不触发"} '
                    f'上次成功={last.strftime("%Y-%m-%d %H:%M") if last else "无记录"}  {spec.description}'
                )
    except Exception as exc:  # noqa: BLE001 - 只读命令，DB 不可用时降级提示
        lines.append(f'  · 读取 sync_logs 失败（数据库不可用？）：{exc}')

    if not resolved.jobs:
        lines.append('  · 没有任何启用的任务（检查 SCHEDULER_*_ENABLED）')
    return lines

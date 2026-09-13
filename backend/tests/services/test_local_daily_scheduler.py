# -*- coding: utf-8 -*-
"""本机每日调度器（#1467）单测。

覆盖：配置解析 / 启动判定（测试·CI·重载父进程）/ 交易日跳过 / 启动补跑 / 单实例锁 /
任务执行时「目标池必须传下去」。**全部离线**：编排器一律替换为替身，不碰任何数据源。
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

import app.services.daily_scheduler as ds

TZ = ZoneInfo('Asia/Shanghai')

# 固定日期，避免用例随「跑测试那天」漂移：
# 2026-09-14 是周一（开盘日），2026-09-12 是周六（休市），2026-10-01 是法定节假日。
MONDAY = date(2026, 9, 14)
SATURDAY = date(2026, 9, 12)
NATIONAL_DAY = date(2026, 10, 1)


def _config(**overrides) -> ds.DailySchedulerConfig:
    """构造测试配置（默认两个任务、不抖动、不需要真实数据库）。"""
    base = {
        'enabled': True,
        'timezone': 'Asia/Shanghai',
        'jobs': (
            ds.DailyJobSpec('temperature', '0 20 * * *', None, '温度计'),
            ds.DailyJobSpec('fund_nav', '30 21 * * *', 'fund', '净值'),
        ),
        'jitter_seconds': 0,
        'skip_non_trading_day': True,
        'run_on_start': False,
        'startup_delay_seconds': 180,
    }
    base.update(overrides)
    return ds.DailySchedulerConfig(**base)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """用例之间清掉模块级单例，避免上一个用例启动的调度器泄漏到下一个。"""
    yield
    ds.shutdown_daily_scheduler(wait=False)
    ds._scheduler = None


# ── 配置解析 ────────────────────────────────────────────────────────────


class TestLoadConfig:
    def test_default_is_disabled_with_two_jobs(self):
        cfg = ds.load_config({})
        # 必须显式打开：否则 conftest 每个用例都会 create_app()，测试里就会真的起抓取线程
        assert cfg.enabled is False
        assert cfg.job_names() == ['temperature', 'fund_nav']
        assert cfg.timezone == ds.DEFAULT_TIMEZONE
        assert cfg.skip_non_trading_day is True
        assert cfg.run_on_start is True
        assert cfg.startup_delay_seconds == ds.DEFAULT_STARTUP_DELAY_SECONDS
        crons = {spec.job_name: spec.cron for spec in cfg.jobs}
        assert crons['temperature'] == ds.DEFAULT_TEMPERATURE_CRON
        assert crons['fund_nav'] == ds.DEFAULT_NAV_CRON

    @pytest.mark.parametrize('raw,expected', [('1', True), ('true', True), ('on', True), ('0', False), ('no', False)])
    def test_enabled_switch_parsing(self, raw, expected):
        assert ds.load_config({ds.ENV_ENABLED: raw}).enabled is expected

    def test_per_job_switch_and_cron_override(self):
        cfg = ds.load_config(
            {
                ds.ENV_ENABLED: 'true',
                ds.ENV_TEMPERATURE_ENABLED: '0',
                ds.ENV_NAV_CRON: '5 22 * * 1-5',
            }
        )
        assert cfg.job_names() == ['fund_nav']
        assert cfg.jobs[0].cron == '5 22 * * 1-5'
        # target_kind 必须留着：丢了它净值 job 会拿到空目标池并「成功」空跑
        assert cfg.jobs[0].target_kind == 'fund'

    def test_timezone_override(self):
        assert ds.load_config({ds.ENV_TIMEZONE: 'UTC'}).timezone == 'UTC'

    def test_invalid_startup_delay_falls_back(self):
        assert ds.load_config({ds.ENV_STARTUP_DELAY: '今天'}).startup_delay_seconds == (
            ds.DEFAULT_STARTUP_DELAY_SECONDS
        )

    def test_jitter_reuses_sync_env(self, monkeypatch):
        """抖动沿用 SYNC_JITTER_SECONDS，不另立一套「抓取礼仪」配置。"""
        monkeypatch.setenv('SYNC_JITTER_SECONDS', '42')
        assert ds.load_config({}).jitter_seconds == 42


# ── 启动判定 ────────────────────────────────────────────────────────────


class TestShouldStart:
    def test_disabled_by_default(self):
        assert ds.should_start(ds.load_config({})) is False

    def test_skipped_in_test_process(self):
        """本用例就跑在 pytest 里。

        conftest 的 app fixture 每个用例都调 create_app()，因此这条守卫必须生效——
        否则测试会真的拉起后台抓取线程并发起网络请求。
        """
        assert ds.should_start(_config()) is False

    def test_starts_when_all_guards_pass(self, monkeypatch):
        monkeypatch.setattr(ds, '_in_test_process', lambda: False)
        monkeypatch.setattr(ds, '_in_ci', lambda: False)
        monkeypatch.setattr(ds, '_is_reloader_parent', lambda debug=None: False)
        assert ds.should_start(_config()) is True

    def test_skipped_in_ci(self, monkeypatch):
        monkeypatch.setattr(ds, '_in_test_process', lambda: False)
        monkeypatch.setattr(ds, '_in_ci', lambda: True)
        monkeypatch.setattr(ds, '_is_reloader_parent', lambda debug=None: False)
        assert ds.should_start(_config()) is False

    def test_skipped_in_reloader_parent(self, monkeypatch):
        monkeypatch.setattr(ds, '_in_test_process', lambda: False)
        monkeypatch.setattr(ds, '_in_ci', lambda: False)
        monkeypatch.setattr(ds, '_is_reloader_parent', lambda debug=None: True)
        assert ds.should_start(_config()) is False

    def test_skipped_without_any_job(self, monkeypatch):
        monkeypatch.setattr(ds, '_in_test_process', lambda: False)
        monkeypatch.setattr(ds, '_in_ci', lambda: False)
        monkeypatch.setattr(ds, '_is_reloader_parent', lambda debug=None: False)
        assert ds.should_start(_config(jobs=())) is False

    def test_reloader_parent_detection(self, monkeypatch):
        # flask run --debug 的执行进程：有 FLASK_RUN_FROM_CLI、没有 WERKZEUG_RUN_MAIN
        monkeypatch.setenv('FLASK_RUN_FROM_CLI', 'true')
        monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
        assert ds._is_reloader_parent(debug=True) is True

        # 重载后的子进程（真正干活的那个）：不该被跳过
        monkeypatch.setenv('WERKZEUG_RUN_MAIN', 'true')
        assert ds._is_reloader_parent(debug=True) is False

        # 非 debug 时 flask run 不起重载器，没有父子之分
        monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
        assert ds._is_reloader_parent(debug=False) is False

        # 非 flask CLI（如 pdm run scheduler-daemon）不参与该判定
        monkeypatch.delenv('FLASK_RUN_FROM_CLI', raising=False)
        assert ds._is_reloader_parent(debug=True) is False


# ── 交易日 ──────────────────────────────────────────────────────────────


class TestRestDay:
    def test_weekend_is_rest_day(self):
        assert ds.is_rest_day(SATURDAY) is True

    def test_holiday_is_rest_day(self):
        assert ds.is_rest_day(NATIONAL_DAY) is True

    def test_ordinary_monday_is_trading_day(self):
        assert ds.is_rest_day(MONDAY) is False


# ── 触发时刻解析 ────────────────────────────────────────────────────────


class TestTodayFireTime:
    def test_returns_today_fire_time(self):
        now = datetime(2026, 9, 14, 10, 0, tzinfo=TZ)
        assert ds.today_fire_time('30 21 * * *', TZ, now) == datetime(2026, 9, 14, 21, 30, tzinfo=TZ)

    def test_none_when_cron_does_not_fire_today(self):
        now = datetime(2026, 9, 14, 10, 0, tzinfo=TZ)  # 周一
        assert ds.today_fire_time('0 3 * * 6', TZ, now) is None  # 仅周六触发


# ── 启动补跑 ────────────────────────────────────────────────────────────


class TestCatchUpTargets:
    def test_nothing_due_before_fire_time(self):
        """早上 9 点启动不该抢跑：数据还没发布，跑一次纯属浪费 + 会写成失败审计。"""
        now = datetime(2026, 9, 14, 9, 0, tzinfo=TZ)
        assert ds.catch_up_targets(_config(), now, {}) == []

    def test_only_passed_job_is_due(self):
        now = datetime(2026, 9, 14, 20, 30, tzinfo=TZ)
        assert ds.catch_up_targets(_config(), now, {}) == ['temperature']

    def test_all_due_after_last_fire_time(self):
        now = datetime(2026, 9, 14, 22, 0, tzinfo=TZ)
        assert ds.catch_up_targets(_config(), now, {}) == ['temperature', 'fund_nav']

    def test_skipped_when_already_succeeded_today(self):
        now = datetime(2026, 9, 14, 23, 0, tzinfo=TZ)
        dates = {'temperature': MONDAY, 'fund_nav': MONDAY}
        assert ds.catch_up_targets(_config(), now, dates) == []

    def test_due_when_last_success_is_stale(self):
        now = datetime(2026, 9, 14, 23, 0, tzinfo=TZ)
        dates = {'temperature': date(2026, 9, 11), 'fund_nav': None}
        assert ds.catch_up_targets(_config(), now, dates) == ['temperature', 'fund_nav']

    def test_rest_day_never_catches_up(self):
        now = datetime(2026, 9, 12, 23, 0, tzinfo=TZ)  # 周六
        assert ds.catch_up_targets(_config(), now, {}) == []

    def test_rest_day_can_be_ignored(self):
        now = datetime(2026, 9, 12, 23, 0, tzinfo=TZ)
        cfg = _config(skip_non_trading_day=False)
        assert ds.catch_up_targets(cfg, now, {}) == ['temperature', 'fund_nav']

    def test_naive_now_is_localized(self):
        now = datetime(2026, 9, 14, 22, 0)  # 无 tzinfo
        assert ds.catch_up_targets(_config(), now, {}) == ['temperature', 'fund_nav']


# ── 执行 ────────────────────────────────────────────────────────────────


class _FakeOrchestrator:
    """编排器替身：记录调用参数，绝不联网。"""

    def __init__(self, result=None, targets=None):
        self.result = result if result is not None else {'job_name': 'x', 'status': 'success', 'stats': {}}
        self.targets_by_kind = targets if targets is not None else {'fund': ['000001'], 'stock': []}
        self.calls = []

    def resolve_targets(self):
        return self.targets_by_kind

    def run_job(self, job_name, full_sync=False, targets=None):
        self.calls.append((job_name, targets))
        return self.result


class TestRunSyncJob:
    def test_resolved_targets_are_passed_down(self, monkeypatch):
        """净值 job 必须拿到「持仓 + 自选」解析出来的代码。

        不传目标时 `FundNavSyncJob` 会因空目标池直接跳过（`_allow_empty_data=True`）
        并返回 success——表现为「调度天天跑、净值天天不更新、且不报错」，
        是最难排查的一类故障，故用测试钉死。
        """
        fake = _FakeOrchestrator()
        monkeypatch.setattr(ds, '_build_orchestrator', lambda db: fake)

        spec = ds.DailyJobSpec('fund_nav', '30 21 * * *', 'fund', '净值')
        result = ds.run_sync_job(spec, jitter_seconds=0)

        assert result['status'] == 'success'
        assert fake.calls == [('fund_nav', ['000001'])]

    def test_targetless_job_passes_none(self, monkeypatch):
        fake = _FakeOrchestrator()
        monkeypatch.setattr(ds, '_build_orchestrator', lambda db: fake)

        spec = ds.DailyJobSpec('temperature', '0 20 * * *', None, '温度计')
        ds.run_sync_job(spec, jitter_seconds=0)

        assert fake.calls == [('temperature', None)]

    def test_exception_is_returned_not_raised(self, monkeypatch):
        """后台线程里抛异常只会变成一行日志，调用方看不到原因——故必须收敛为结果。"""

        def _boom(db):
            raise RuntimeError('数据源不可用')

        monkeypatch.setattr(ds, '_build_orchestrator', _boom)
        spec = ds.DailyJobSpec('fund_nav', '30 21 * * *', 'fund', '净值')

        result = ds.run_sync_job(spec, jitter_seconds=0)

        assert result['status'] == 'error'
        assert '数据源不可用' in result['error']

    def test_jitter_applied_when_configured(self, monkeypatch):
        calls = []
        monkeypatch.setattr(ds, 'apply_jitter', lambda window, label='': calls.append((window, label)))
        monkeypatch.setattr(ds, '_build_orchestrator', lambda db: _FakeOrchestrator())

        ds.run_sync_job(ds.DailyJobSpec('fund_nav', '30 21 * * *', 'fund', '净值'), jitter_seconds=600)

        assert calls == [(600, '每日调度 fund_nav')]


# ── 单实例锁与调度器生命周期 ────────────────────────────────────────────


class TestSingleInstanceLock:
    def test_second_scheduler_cannot_start(self, tmp_path):
        cfg = _config(lock_file=tmp_path / 'daily_scheduler.lock')

        first = ds.DailyScheduler(cfg)
        assert first.start() is True
        try:
            assert first.running is True
            # 同机第二份（如 dev 的重载子进程、或应用 + 守护进程同时在跑）必须起不来
            second = ds.DailyScheduler(cfg)
            assert second.start() is False
            assert second.running is False
        finally:
            first.shutdown()

        # 释放后立刻可再启动：锁由内核回收，不存在需要人工清理的 stale 锁
        third = ds.DailyScheduler(cfg)
        assert third.start() is True
        third.shutdown()

    def test_registers_cron_jobs_and_startup_catch_up(self, tmp_path):
        cfg = _config(lock_file=tmp_path / 's1.lock', run_on_start=True)
        scheduler = ds.DailyScheduler(cfg)
        assert scheduler.start() is True
        try:
            ids = {job.id for job in scheduler._scheduler.get_jobs()}
        finally:
            scheduler.shutdown()
        assert ids == {'temperature', 'fund_nav', 'startup_catch_up'}

    def test_no_startup_job_when_run_on_start_disabled(self, tmp_path):
        cfg = _config(lock_file=tmp_path / 's2.lock', run_on_start=False)
        scheduler = ds.DailyScheduler(cfg)
        assert scheduler.start() is True
        try:
            ids = {job.id for job in scheduler._scheduler.get_jobs()}
        finally:
            scheduler.shutdown()
        assert ids == {'temperature', 'fund_nav'}

    def test_start_daily_scheduler_is_noop_in_test_process(self, tmp_path):
        assert ds.start_daily_scheduler(_config(lock_file=tmp_path / 's3.lock')) is None
        assert ds.get_daily_scheduler() is None

    def test_start_daily_scheduler_is_idempotent(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ds, '_in_test_process', lambda: False)
        monkeypatch.setattr(ds, '_in_ci', lambda: False)
        monkeypatch.setattr(ds, '_is_reloader_parent', lambda debug=None: False)

        cfg = _config(lock_file=tmp_path / 's4.lock')
        scheduler = ds.start_daily_scheduler(cfg)
        try:
            assert scheduler is not None
            assert scheduler.running is True
            # 重复调用（如 create_app() 被再次执行）不得起第二份
            assert ds.start_daily_scheduler(cfg) is scheduler
        finally:
            ds.shutdown_daily_scheduler()

        assert ds.get_daily_scheduler() is None


# ── 状态输出 ────────────────────────────────────────────────────────────


class TestDescribeStatus:
    def test_mentions_jobs_and_lock_state(self, tmp_path):
        lines = ds.describe_status(_config(lock_file=tmp_path / 's5.lock'))
        text = '\n'.join(lines)
        assert 'temperature' in text
        assert 'fund_nav' in text
        # 测试进程没有持有锁 → 应报「未运行」
        assert '未运行' in text

    def test_reports_running_when_lock_held(self, tmp_path):
        cfg = _config(lock_file=tmp_path / 's6.lock')
        holder = ds.DailyScheduler(cfg)
        assert holder.start() is True
        try:
            assert '运行中' in '\n'.join(ds.describe_status(cfg))
        finally:
            holder.shutdown()


# ── 文件锁 ──────────────────────────────────────────────────────────────


class TestFileLock:
    def test_second_acquire_fails_until_release(self, tmp_path):
        from app.core.file_lock import acquire_lock, release_lock

        lock = tmp_path / 'probe.lock'
        ok1, fd1 = acquire_lock(lock)
        assert ok1 is True
        ok2, fd2 = acquire_lock(lock)
        assert (ok2, fd2) == (False, None)
        release_lock(fd1)
        ok3, fd3 = acquire_lock(lock)
        assert ok3 is True
        release_lock(fd3)

    def test_release_is_idempotent_for_none(self):
        from app.core.file_lock import release_lock

        release_lock(None)  # 不抛异常即可

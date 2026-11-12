# -*- coding: utf-8 -*-
"""本地巡检通道（#3078）。

这一层的价值不是「算出什么」，而是三条**准入边界**是否真的收紧：

1. 清单是白名单——新增一项必须同时改本文件，那是 review 会看到的闸门；
2. 巡检不与 daily job 撞名（撞了 APScheduler 会用 `replace_existing` 静默顶掉一个 job）；
3. 巡检自己落的 stats 必须能被自己读回来——走编排器审计会用 `str(dict)` 落库，而
   `last_guard_stats` 用 `json.loads` 读，结果是「基线永远读不回来、判定永远停在首次」，
   不报错、日志全绿（本文件最后两组用例就是钉这个）。
"""

from types import SimpleNamespace

import pytest
import sqlalchemy
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import database
from app.models.sync_log import SyncLog
from app.services import cold_set_check, cold_set_guard, local_checks
from app.services.cold_set_check import CheckOutcome
from app.services.cold_set_guard import GuardReport
from app.services.daily_scheduler import _JOB_TEMPLATES, load_config

_DDL = """
CREATE TABLE sync_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    full_sync BOOLEAN,
    stats TEXT,
    error_detail TEXT,
    data_source VARCHAR(50),
    data_source_version VARCHAR(20),
    started_at DATETIME NOT NULL,
    finished_at DATETIME,
    duration_seconds FLOAT
)
"""


def _empty_db():
    """只有 `sync_logs` 的内存库：巡检的写与读都只碰这张表。"""
    engine = sqlalchemy.create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text(_DDL))
    return Session(engine)


class TestCheckWhitelist:
    def test_only_whitelisted_checks_are_registered(self):
        """**白名单**：新增巡检必须改这一行——这就是这条通道的闸门。

        允许进来的三条判据见 `local_checks` 模块 docstring（零外部请求 / 只读业务表 /
        判定口径已存在）。「想让它定期跑」不是理由。
        """
        assert [c.job_name for c in local_checks.build_checks({})] == [cold_set_guard.GUARD_JOB_NAME]

    def test_check_names_do_not_collide_with_daily_jobs(self):
        """与编排器 job 撞名会让 APScheduler 静默顶掉一个日跑 job。"""
        daily = {row[0] for row in _JOB_TEMPLATES}
        assert not ({c.job_name for c in local_checks.build_checks({})} & daily)

    def test_job_name_matches_guard_constant(self):
        """名字必须与守卫落库时用的常量同源，否则基线读不回来。"""
        spec = local_checks.build_checks({})[0]
        assert spec.job_name == cold_set_guard.GUARD_JOB_NAME

    def test_cron_is_valid_and_weekly(self):
        """周频而非日频：膨胀来自回填，不来自日更；同时必须是能解析的五段 cron。"""
        from apscheduler.triggers.cron import CronTrigger

        cron = local_checks.build_checks({})[0].cron
        CronTrigger.from_crontab(cron)  # 解析失败即抛
        assert cron.split()[4] != '*', '巡检不该按天跑'

    def test_can_be_disabled(self):
        assert local_checks.build_checks({local_checks.ENV_COLD_SET_GUARD_ENABLED: '0'}) == ()

    def test_cron_can_be_overridden(self):
        spec = local_checks.build_checks({local_checks.ENV_COLD_SET_GUARD_CRON: '0 5 * * sun'})[0]
        assert spec.cron == '0 5 * * sun'

    def test_scheduler_config_carries_checks(self):
        """接线：配置里拿得到巡检，否则注册环节永远为空。"""
        cfg = load_config({local_checks.ENV_COLD_SET_GUARD_ENABLED: '0'})
        assert cfg.checks == ()
        assert load_config({}).checks, '缺省应启用（否则守卫又回到「只有人手点才会跑」）'


class TestRunLocalCheck:
    def test_runner_errors_are_swallowed(self):
        """后台线程里抛出的异常只会变成一行日志，必须收敛成结构化结果。"""

        def boom():
            raise RuntimeError('炸了')

        spec = local_checks.LocalCheckSpec(job_name='x', cron='0 4 * * mon', runner=boom, description='')
        result = local_checks.run_local_check(spec)
        assert result['status'] == 'error'
        assert '炸了' in result['error']

    def test_bloated_is_not_reported_as_success(self, monkeypatch):
        """膨胀要打 warning，不能被记成 success（否则「一跑就膨胀」看不出来）。"""
        fake = CheckOutcome(
            report=GuardReport(cutoff='2025-11-12', total_stale=99999, bloated=True), comparable=None, days=None
        )
        monkeypatch.setattr(cold_set_check, 'run_check_and_record', lambda db: fake)
        monkeypatch.setattr(database, 'get_session', lambda: SimpleNamespace(close=lambda: None))

        result = local_checks._run_cold_set_bloat_guard()
        assert result['status'] == 'bloated'
        assert result['job_name'] == cold_set_guard.GUARD_JOB_NAME
        assert result['stats']['bloated'] is True


class TestStatsRoundTrip:
    """巡检落库的 stats 必须能被自己读回来（#3078 的核心闭环）。"""

    def test_first_run_establishes_baseline(self, monkeypatch):
        db = _empty_db()
        monkeypatch.setattr(
            cold_set_guard, 'measure', lambda db, keep_days: GuardReport(cutoff='2025-11-12', total_stale=100)
        )

        outcome = cold_set_check.run_check_and_record(db)
        assert outcome.report.bloated is False, '首次巡检只建基线，不判定'

        stats = cold_set_guard.last_guard_stats(db)
        assert stats is not None, 'stats 读不回来 ⇒ 判定永远停在「首次巡检」'
        assert stats['total_stale'] == 100
        assert stats['cutoff'] == '2025-11-12'

    def test_second_run_compares_against_recorded_baseline(self, monkeypatch):
        db = _empty_db()
        monkeypatch.setattr(
            cold_set_guard, 'measure', lambda db, keep_days: GuardReport(cutoff='2025-11-12', total_stale=100)
        )
        cold_set_check.run_check_and_record(db)

        monkeypatch.setattr(
            cold_set_guard, 'measure', lambda db, keep_days: GuardReport(cutoff='2025-11-19', total_stale=160)
        )
        outcome = cold_set_check.run_check_and_record(db)
        assert outcome.report.prev_stale == 100
        assert outcome.report.growth == 60
        assert outcome.prev_cutoff == '2025-11-12'

    def test_written_as_json_not_repr(self):
        """落库必须是 json：编排器的 `str(dict)` 写法读不回来（单引号）。"""
        import json

        db = _empty_db()
        cold_set_guard.record(db, GuardReport(cutoff='2025-11-12', total_stale=7))
        raw = db.execute(text('SELECT stats FROM sync_logs')).scalar()
        assert json.loads(raw)['total_stale'] == 7, 'stats 不是合法 json'


class TestLastRunAt:
    def test_sees_non_success_status(self):
        """`get_last_sync_time` 只认 success，而巡检落的是 ok/bloated——两回事。"""
        db = _empty_db()
        cold_set_guard.record(db, GuardReport(cutoff='2025-11-12', total_stale=1, bloated=True))

        assert SyncLog.get_last_sync_time(db, cold_set_guard.GUARD_JOB_NAME) is None, '这正是要避开的读法'
        assert local_checks.last_run_at(db, cold_set_guard.GUARD_JOB_NAME) is not None

    def test_never_run_returns_none(self):
        assert local_checks.last_run_at(_empty_db(), cold_set_guard.GUARD_JOB_NAME) is None


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))

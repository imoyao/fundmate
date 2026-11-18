# -*- coding: utf-8 -*-
"""#2872 回归：冷集写入硬上限（写入期范围强制）。

判据重点不是「数字算得对」，而是三条**失效即事故**的行为：

1. 窗口内 / 热集的行**一行都不能被误拦**——误拦会把正常的每日增量同步打成红灯，
   而 `SyncLog.get_last_sync_time` 只认 `status='success'`，一次误拦会把增量起点
   永久钉死（#1550 实测静默失败一个月）；
2. 超上限必须**抛错**而不是静默少写——静默丢数据会让 `stats['success']` 与库里
   行数对不上，且冷/热集会变（今天不持有、明天建仓），丢掉的缺口历史补不回来；
3. 热集口径不可用时必须 **fail-open**（放行 + WARNING）——守卫自身故障不得阻断同步。
"""

from datetime import date, timedelta

import pytest

from app.domains.funds.models import DailyWorth, Fund
from app.services import cold_set_write_scope as scope
from app.services.cold_set_write_scope import (
    count_cold_out_of_window,
    enforce_cold_write_cap,
    load_hot_codes,
)
from app.services.sync.jobs.fund_nav_job import FundNavSyncJob

TODAY = date(2026, 11, 5)
RECENT = TODAY - timedelta(days=30)
OLD = TODAY - timedelta(days=400)


def _rec(code, d):
    return {'fund_code': code, 'date': d, 'unit_nav': 1.0}


class TestCountColdOutOfWindow:
    def test_hot_code_old_rows_not_counted(self):
        """热集全留：持有/自选/有流水的标的，多老的历史都不算溢出。"""
        assert count_cold_out_of_window([_rec('000001', OLD)], {'000001'}, today=TODAY) == 0

    def test_cold_code_within_window_not_counted(self):
        """冷集只留近 N 天：窗口内的行是策略允许的部分，不计入。"""
        assert count_cold_out_of_window([_rec('000002', RECENT)], set(), today=TODAY) == 0

    def test_cold_code_out_of_window_counted(self):
        assert count_cold_out_of_window([_rec('000002', OLD)], set(), today=TODAY) == 1

    def test_unavailable_hot_set_is_fail_open(self):
        """热集口径拿不到 ⇒ 返回 0（本次不判定），绝不因为守卫故障拦下正常写入。"""
        assert count_cold_out_of_window([_rec('000002', OLD)], None, today=TODAY) == 0

    def test_non_date_value_not_counted(self):
        """异常日期不在本函数判定（校验阶段负责），避免鸭子类型误判。"""
        assert count_cold_out_of_window([{'fund_code': '000002', 'date': '2020-01-01'}], set(), today=TODAY) == 0

    def test_window_boundary_is_inclusive(self):
        """恰好落在 cutoff 当天的行算「窗口内」，与清理脚本 `date < cutoff` 口径一致。"""
        cutoff_day = TODAY - timedelta(days=365)
        assert count_cold_out_of_window([_rec('000002', cutoff_day)], set(), today=TODAY) == 0
        assert count_cold_out_of_window([_rec('000002', cutoff_day - timedelta(days=1))], set(), today=TODAY) == 1


class TestEnforceColdWriteCap:
    def test_at_cap_passes(self, db):
        records = [_rec('000002', OLD) for _ in range(3)]
        assert enforce_cold_write_cap(db, records, job_name='fund_nav', cap=3, today=TODAY) == 3

    def test_over_cap_raises(self, db):
        records = [_rec('000002', OLD) for _ in range(4)]
        with pytest.raises(ValueError) as exc:
            enforce_cold_write_cap(db, records, job_name='fund_nav', cap=3, today=TODAY)
        message = str(exc.value)
        assert '冷集写入超上限' in message
        # 处置建议必须在错误里：运维能看到的只有这条日志
        assert '--targets' in message and '自选' in message

    def test_hot_set_unavailable_does_not_raise(self, db, monkeypatch):
        """热集查询抛 SystemExit / 异常都不得冒泡（守卫故障 ≠ 同步失败）。"""
        monkeypatch.setattr(scope, '_hot_codes', lambda _db: (_ for _ in ()).throw(SystemExit('来源表缺失')))
        records = [_rec('000002', OLD) for _ in range(10)]
        assert enforce_cold_write_cap(db, records, job_name='fund_nav', cap=1, today=TODAY) == 0

    def test_load_hot_codes_returns_none_when_source_missing(self, db, monkeypatch):
        monkeypatch.setattr(scope, '_hot_codes', lambda _db: (_ for _ in ()).throw(SystemExit('来源表缺失')))
        assert load_hot_codes(db) is None


class TestFundNavJobWriteCap:
    """job 级：上限必须卡在**落库之前**，且上限按模块常量可调（便于按环境调参）。"""

    @pytest.fixture
    def job(self, db):
        return FundNavSyncJob(adapter=object(), db=db)

    @staticmethod
    def _ensure_fund(db, code):
        if not db.query(Fund).filter_by(fund_code=code).first():
            db.add(Fund(fund_code=code, name=f'测试基金{code}'))
            db.flush()

    def test_over_cap_rejects_whole_batch_without_writing(self, job, db, monkeypatch):
        self._ensure_fund(db, '000002')
        monkeypatch.setattr(scope, 'MAX_COLD_ROWS_PER_WRITE', 2)

        records = [_rec('000002', OLD - timedelta(days=i)) for i in range(3)]
        with pytest.raises(ValueError):
            job._save_data(records)

        assert db.query(DailyWorth).count() == 0, '超限必须整批拒绝，不能先写一半'

    def test_within_cap_writes_rows(self, job, db, monkeypatch):
        self._ensure_fund(db, '000002')
        monkeypatch.setattr(scope, 'MAX_COLD_ROWS_PER_WRITE', 3)

        job._save_data([_rec('000002', OLD - timedelta(days=i)) for i in range(3)])
        assert db.query(DailyWorth).count() == 3
        assert job.stats['cold_set_overflow'] == 3

    def test_hot_code_full_history_is_not_limited(self, job, db, monkeypatch):
        """热集标的不受限：这是「补 5 只自选基金全历史」的正常用法。"""
        self._ensure_fund(db, '000001')
        monkeypatch.setattr(scope, 'MAX_COLD_ROWS_PER_WRITE', 1)
        monkeypatch.setattr(scope, 'load_hot_codes', lambda _db: {'000001'})

        job._save_data([_rec('000001', OLD - timedelta(days=i)) for i in range(5)])
        assert db.query(DailyWorth).count() == 5
        assert job.stats['cold_set_overflow'] == 0

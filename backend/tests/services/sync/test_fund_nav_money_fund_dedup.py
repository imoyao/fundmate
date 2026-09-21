# -*- coding: utf-8 -*-
"""#1550 回归测试：货基净值必须按目标表去重，且写入不得被单条重复拖垮。

案发现场（2026-09-16 21:30 本机常驻调度）：
    sqlite3.IntegrityError: UNIQUE constraint failed:
      money_fund_daily_worth.fund_code, money_fund_daily_worth.date

根因链（旧代码）：
1. `FundNavSyncJob._deduplicate` 只查 `DailyWorth`，而 `_save_data` 把货基记录写进
   `MoneyFundDailyWorth` —— 货基记录等于「从未去重」，必撞唯一约束；
2. `SyncJob.run` 重试分支不 rollback Session，第 2/3 次必然 PendingRollbackError；
3. `orchestrator.run_job` 在中毒 Session 上写 sync_logs → 异常冒泡，
   审计表零记录（fund_nav 自 2026-08-14 起静默失败一个月）。
"""

from datetime import date, datetime

import pytest

from app.domains.funds.models import DailyWorth, Fund, MoneyFundDailyWorth
from app.models.sync_log import SyncLog
from app.services import job_base as base_module
from app.services.job_base import JobStatus
from app.services.sync.jobs.fund_nav_job import FundNavSyncJob


class StubFundNavAdapter:
    """最小适配器替身：固定返回一组净值记录"""

    def __init__(self, records):
        self._records = records

    def fetch_fund_nav(self, fund_code, start_date=None, end_date=None):
        return list(self._records)

    def get_name(self):
        return 'stub'

    def get_version(self):
        return '0'


def _ensure_fund(db, code: str, name: str = '测试基金') -> None:
    """两张净值表的 fund_code 外键都指向 funds"""
    if not db.query(Fund).filter_by(fund_code=code).first():
        db.add(Fund(fund_code=code, name=name))
        db.flush()


class TestMoneyFundDeduplicate:
    """货基去重必须查 money_fund_daily_worth，而不是 daily_worth"""

    @pytest.fixture
    def job(self, db):
        return FundNavSyncJob(adapter=object(), db=db)

    def test_existing_money_fund_row_is_dropped(self, job, db):
        """money_fund_daily_worth 已有 (026029, 2026-08-13) → 必须从待写列表里剔除"""
        _ensure_fund(db, '026029', '银河水星现金添利货币')
        db.add(MoneyFundDailyWorth(fund_code='026029', date=date(2026, 8, 13), nav_per_10k=0.2293))
        db.commit()

        data = [
            {'fund_code': '026029', 'date': date(2026, 8, 13), 'unit_nav': 0.2293, 'is_money_fund': True},
            {'fund_code': '026029', 'date': date(2026, 8, 14), 'unit_nav': 0.0612, 'is_money_fund': True},
            {'fund_code': '026029', 'date': date(2026, 8, 16), 'unit_nav': 0.4595, 'is_money_fund': True},
        ]
        kept = job._deduplicate(data)

        keys = {(item['fund_code'], item['date']) for item in kept}
        assert ('026029', date(2026, 8, 13)) not in keys, '货基存量行未被剔除 → 必撞唯一约束'
        assert keys == {('026029', date(2026, 8, 14)), ('026029', date(2026, 8, 16))}

    def test_normal_and_money_dedup_do_not_cross_tables(self, job, db):
        """两张表各自去重：daily_worth 的存量不该「吃掉」货基记录，反之亦然"""
        _ensure_fund(db, '018868', '兴全品质甄选混合A')
        _ensure_fund(db, '004369', '前海开源聚财宝B')
        db.add(DailyWorth(fund_code='018868', date=date(2026, 9, 15), unit_nav=1.111))
        db.add(MoneyFundDailyWorth(fund_code='004369', date=date(2026, 9, 15), nav_per_10k=0.2574))
        db.commit()

        data = [
            # 普通基金：与 daily_worth 撞 → 剔除
            {'fund_code': '018868', 'date': date(2026, 9, 15), 'unit_nav': 1.111, 'is_money_fund': False},
            # 货基：与 money_fund_daily_worth 撞 → 剔除
            {'fund_code': '004369', 'date': date(2026, 9, 15), 'unit_nav': 0.2574, 'is_money_fund': True},
            {'fund_code': '018868', 'date': date(2026, 9, 16), 'unit_nav': 1.222, 'is_money_fund': False},
            {'fund_code': '004369', 'date': date(2026, 9, 16), 'unit_nav': 0.7355, 'is_money_fund': True},
        ]
        kept = {(item['fund_code'], item['date']) for item in job._deduplicate(data)}

        assert kept == {('018868', date(2026, 9, 16)), ('004369', date(2026, 9, 16))}

    def test_save_data_survives_single_duplicate(self, job, db):
        """DB 端已有重复行（去重漏判 / 并发写）时，同批其余记录仍须落库、不得抛异常"""
        _ensure_fund(db, '026029')
        db.add(MoneyFundDailyWorth(fund_code='026029', date=date(2026, 8, 13), nav_per_10k=0.2293))
        db.commit()

        records = [
            {'fund_code': '026029', 'date': date(2026, 8, 13), 'unit_nav': 0.2293, 'is_money_fund': True},
            {'fund_code': '026029', 'date': date(2026, 8, 16), 'unit_nav': 0.4595, 'is_money_fund': True},
        ]
        job._save_data(records)  # 旧实现：整条 executemany 抛 IntegrityError

        rows = {r.date for r in db.query(MoneyFundDailyWorth).filter_by(fund_code='026029').all()}
        assert rows == {date(2026, 8, 13), date(2026, 8, 16)}, '重复行不该拖垮同批其余记录'

    def test_run_reproduces_and_survives_the_incident(self, job, db):
        """端到端复现案发场景：货基存量 08-13/08-14 + 增量窗口自 08-13 起"""
        _ensure_fund(db, '026029', '银河水星现金添利货币')
        db.add(MoneyFundDailyWorth(fund_code='026029', date=date(2026, 8, 13), nav_per_10k=0.2293))
        db.add(MoneyFundDailyWorth(fund_code='026029', date=date(2026, 8, 14), nav_per_10k=0.0612))
        db.commit()

        job.adapter = StubFundNavAdapter(
            [
                {'fund_code': '026029', 'date': date(2026, 8, 13), 'unit_nav': 0.2293, 'is_money_fund': True},
                {'fund_code': '026029', 'date': date(2026, 8, 14), 'unit_nav': 0.0612, 'is_money_fund': True},
                {'fund_code': '026029', 'date': date(2026, 8, 16), 'unit_nav': 0.4595, 'is_money_fund': True},
            ]
        )

        result = job.run(full_sync=False, targets=['026029'])

        assert result['status'] == JobStatus.SUCCESS.value
        assert result['stats']['success'] == 1, '只有 08-16 属新增，另两条应被去重跳过'
        rows = {r.date for r in db.query(MoneyFundDailyWorth).filter_by(fund_code='026029').all()}
        assert rows == {date(2026, 8, 13), date(2026, 8, 14), date(2026, 8, 16)}


class TestRetryRollsBackSession:
    """#1550 第 2 环：重试前必须 rollback，否则重试必然连挂三次"""

    def test_retry_after_flush_failure_uses_fresh_session(self, db, monkeypatch):
        _ensure_fund(db, '000001')
        db.add(DailyWorth(fund_code='000001', date=date(2025, 1, 1), unit_nav=1.0))
        db.commit()

        job = FundNavSyncJob(
            adapter=StubFundNavAdapter([{'fund_code': '000001', 'date': date(2025, 1, 2), 'unit_nav': 1.1}]), db=db
        )
        monkeypatch.setattr(base_module.time, 'sleep', lambda *_: None)

        calls = {'n': 0}
        original_save = FundNavSyncJob._save_data

        def flaky_save(self, new_data):
            calls['n'] += 1
            if calls['n'] == 1:
                # 模拟真实案发：flush 阶段撞唯一约束，Session 进入「必须 rollback」
                self.db.add(DailyWorth(fund_code='000001', date=date(2025, 1, 1), unit_nav=1.0))
                self.db.flush()
            return original_save(self, new_data)

        monkeypatch.setattr(FundNavSyncJob, '_save_data', flaky_save)

        result = job.run(full_sync=False, targets=['000001'])

        assert calls['n'] == 2, '第一次失败后必须真的重试一次'
        assert result['status'] == JobStatus.SUCCESS.value, (
            f'重试仍失败（Session 未 rollback）: {result["stats"].get("error")}'
        )
        assert db.query(DailyWorth).filter_by(fund_code='000001', date=date(2025, 1, 2)).count() == 1

    def test_session_usable_after_giving_up(self, db, monkeypatch):
        """放弃重试后 Session 必须干净——否则 run_all_jobs 的后续 job 一并受害"""
        _ensure_fund(db, '000002')
        db.add(DailyWorth(fund_code='000002', date=date(2025, 1, 1), unit_nav=1.0))
        db.commit()

        job = FundNavSyncJob(
            adapter=StubFundNavAdapter([{'fund_code': '000002', 'date': date(2025, 1, 2), 'unit_nav': 1.1}]), db=db
        )
        monkeypatch.setattr(base_module.time, 'sleep', lambda *_: None)
        monkeypatch.setattr(base_module, 'MAX_RETRIES', 1)

        def duplicate_flush(self, new_data):
            # 与预置行同键 → flush 撞唯一约束 → Session 进入「必须 rollback」
            self.db.add(DailyWorth(fund_code='000002', date=date(2025, 1, 1), unit_nav=1.0))
            self.db.flush()

        monkeypatch.setattr(FundNavSyncJob, '_save_data', duplicate_flush)

        result = job.run(full_sync=False, targets=['000002'])

        assert result['status'] == JobStatus.MANUAL_INTERVENTION.value
        # 中毒的 Session 会在下一次 flush 时抛 PendingRollbackError；这里必须能正常落库
        db.add(SyncLog(job_name='probe', status='success', started_at=datetime(2025, 1, 1)))
        db.commit()
        assert db.query(SyncLog).filter_by(job_name='probe').count() == 1

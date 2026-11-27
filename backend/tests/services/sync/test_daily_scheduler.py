# -*- coding: utf-8 -*-
"""测试每日调度：AssetSnapshotJob（#1182）与 PositionPriceSyncJob（#1104）的注册与落账。"""

import datetime as dt

from app.domains.ledgers.models import Ledger
from app.domains.summary.models import AssetSnapshot
from app.services.sync.jobs.periodic_review_job import _due_period_key
from app.services.sync.orchestrator import DataSyncOrchestrator


class TestDailyScheduler:
    def test_asset_snapshot_job_registered(self, db):
        """Orchestrator 必须注册 asset_snapshot job（run_all_jobs 才会在末尾触发）。"""
        orch = DataSyncOrchestrator(db)
        assert 'asset_snapshot' in orch.jobs
        assert orch.jobs['asset_snapshot'].get_name() == 'asset_snapshot'

    def test_position_price_job_registered(self, db):
        """#1104：持仓现价回写必须注册，且能经编排器统一入口被调度器/CLI 触发。"""
        orch = DataSyncOrchestrator(db)
        assert 'position_price' in orch.jobs
        assert orch.jobs['position_price'].get_name() == 'position_price'

    def test_periodic_review_job_registered(self, db):
        """#875：定期复盘报告生成必须注册（挂进每日调度，fund_nav 之后触发）。"""
        orch = DataSyncOrchestrator(db)
        assert 'periodic_review' in orch.jobs
        assert orch.jobs['periodic_review'].get_name() == 'periodic_review'

    def test_run_position_price_success_on_empty_db(self, db):
        """空库无持仓 → 幂等 no-op，返回 success（不报错、不抛异常）。"""
        orch = DataSyncOrchestrator(db)
        result = orch.run_job('position_price')
        assert result['status'] == 'success'
        assert result['stats']['total'] == 0

    def test_run_asset_snapshot_success_on_empty_db(self, db):
        """空库无 family → 幂等 no-op，仍返回 success（不报错、不抛异常）。"""
        orch = DataSyncOrchestrator(db)
        result = orch.run_job('asset_snapshot')
        assert result['status'] == 'success'
        # 幂等 no-op：空库未写入任何快照行
        assert db.query(AssetSnapshot).count() == 0

    def test_run_periodic_review_success_on_empty_db(self, db):
        """空库无 family → 幂等 no-op，仍返回 success。"""
        orch = DataSyncOrchestrator(db)
        result = orch.run_job('periodic_review')
        assert result['status'] == 'success'
        assert result['stats']['total'] == 0

    def test_run_asset_snapshot_writes_family_snapshot(self, db):
        """有 ledger(family_id=1) 时，应为该家庭落当日快照（家庭级 + 账户级）。"""
        ledger = Ledger(name='测试账户', ledger_type='bank', family_id=1)
        db.add(ledger)
        db.commit()

        orch = DataSyncOrchestrator(db)
        result = orch.run_job('asset_snapshot')
        assert result['status'] == 'success'
        assert result.get('stats', {}).get('success') == 1

        snap = db.query(AssetSnapshot).filter(AssetSnapshot.family_id == 1).first()
        assert snap is not None
        # #863 P1-5：本测试家庭仅有银行台账、无货基持仓，write_asset_snapshot 对无货基
        # 家庭写 None（展示层再按 0.0 处理，见 summary_service._snapshot_payload）。
        assert snap.money_fund_income_cents is None


class TestDuePeriodKey:
    """#875：就绪判定——「今天所属周期」是否已到最后一个交易日。"""

    def test_before_last_trading_day_not_due(self):
        # 2026-11-26（周四）还不是本周最后交易日（周五 11-27），周报不 due
        assert _due_period_key(dt.date(2026, 11, 26), 'week') is None

    def test_on_last_trading_day_due(self):
        # 2026-11-27（周五）是本周最后交易日 → 周报 due（「周五汇总」落地）
        assert _due_period_key(dt.date(2026, 11, 27), 'week') == '2026-W48'

    def test_weekend_still_due_until_next_week(self):
        # 周末仍在「本周最后交易日之后」，仍 due（幂等由服务层兜）
        assert _due_period_key(dt.date(2026, 11, 28), 'week') == '2026-W48'
        assert _due_period_key(dt.date(2026, 11, 29), 'week') == '2026-W48'

    def test_next_week_resets(self):
        # 11-30（周一）进入新一周 W49，其最后交易日未到 → 不 due
        assert _due_period_key(dt.date(2026, 11, 30), 'week') is None

    def test_month_due_on_last_day(self):
        # 2026-11-30 是 11 月最后交易日（周一，交易日）→ 月报 due
        assert _due_period_key(dt.date(2026, 11, 30), 'month') == '2026-11'

    def test_year_not_due_mid_year(self):
        assert _due_period_key(dt.date(2026, 6, 15), 'year') is None

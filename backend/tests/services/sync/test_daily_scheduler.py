# -*- coding: utf-8 -*-
"""测试 #1182 每日调度：AssetSnapshotJob 注册与落账。"""

from app.domains.ledgers.models import Ledger
from app.domains.summary.models import AssetSnapshot
from app.services.sync.orchestrator import DataSyncOrchestrator


class TestDailyScheduler:
    def test_asset_snapshot_job_registered(self, db):
        """Orchestrator 必须注册 asset_snapshot job（run_all_jobs 才会在末尾触发）。"""
        orch = DataSyncOrchestrator(db)
        assert 'asset_snapshot' in orch.jobs
        assert orch.jobs['asset_snapshot'].get_name() == 'asset_snapshot'

    def test_run_asset_snapshot_success_on_empty_db(self, db):
        """空库无 family → 幂等 no-op，仍返回 success（不报错、不抛异常）。"""
        orch = DataSyncOrchestrator(db)
        result = orch.run_job('asset_snapshot')
        assert result['status'] == 'success'

    def test_run_asset_snapshot_writes_family_snapshot(self, db):
        """有 ledger(family_id=1) 时，应为该家庭落当日快照（家庭级 + 账户级）。"""
        ledger = Ledger(name='测试账户', ledger_type='bank', family_id=1)
        db.add(ledger)
        db.commit()

        orch = DataSyncOrchestrator(db)
        result = orch.run_job('asset_snapshot')
        assert result['status'] == 'success'
        assert result['stats']['success'] == 1

        snap = db.query(AssetSnapshot).filter(AssetSnapshot.family_id == 1).first()
        assert snap is not None
        # 资产快照表在 #863（PR #1306）落地了货基每日收益列 money_fund_income_cents，
        # 该列随 #1306 合入 dev 后由 write_asset_snapshot 写入；此处仅在列存在时校验，
        # 使本测试在 #1306 合入前也能独立通过。
        if hasattr(AssetSnapshot, 'money_fund_income_cents'):
            assert snap.money_fund_income_cents is not None

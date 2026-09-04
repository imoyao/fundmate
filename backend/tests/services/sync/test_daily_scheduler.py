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
        # 幂等 no-op：空库未写入任何快照行
        assert db.query(AssetSnapshot).count() == 0

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

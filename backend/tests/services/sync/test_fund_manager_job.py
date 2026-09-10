# -*- coding: utf-8 -*-
"""测试 FundManagerSyncJob"""

from unittest.mock import MagicMock

import pytest

from app.domains.funds.models import Fund, FundManager, Manager
from app.services.sync.jobs.fund_manager_job import FundManagerSyncJob


class TestFundManagerSyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        return FundManagerSyncJob(adapter, db)

    def test_run_integration(self, job, db):
        """端到端测试：同步基金经理并建立关联"""
        fund = Fund(fund_code='000001', name='测试基金')
        db.add(fund)
        db.commit()

        job.adapter.fetch_fund_manager.return_value = [
            {'name': '张三', 'mgr_code': 'MGR001', 'appointment_date': None},
            {'name': '李四', 'mgr_code': 'MGR002', 'appointment_date': None},
        ]

        result = job.run(full_sync=True, targets=['000001'])
        assert result['status'] == 'success'
        assert result['stats']['success'] == 2
        assert result['stats']['total'] == 1

        mgrs = db.query(Manager).all()
        assert len(mgrs) == 2

        fund_mgr_rows = db.query(FundManager).all()
        assert len(fund_mgr_rows) == 2

    # ── 目标语义锁定（#1402）──
    #
    # 本 job 的 targets 语义与 fund_type_job 一致，且完全由 base.run 分流：
    #   targets is None → 全量回填（取库内全部基金）
    #   targets == []   → 「无目标跳过」，不抓取
    #   targets 非空    → 只处理目标
    # 下面三条把三种分支都钉死，防止后来人把「空 targets」误改成全量（或反之）。

    def test_none_targets_means_full_backfill(self, job, db):
        """targets 缺省（None）→ 全量回填：遍历库内全部基金"""
        db.add_all([Fund(fund_code='000001', name='基金A'), Fund(fund_code='000002', name='基金B')])
        db.commit()
        job.adapter.fetch_fund_manager.return_value = []

        result = job.run(full_sync=True)  # 不传 targets 即 None
        assert result['status'] == 'success'
        called = sorted(call.args[0] for call in job.adapter.fetch_fund_manager.call_args_list)
        assert called == ['000001', '000002']

    def test_empty_target_list_skips_without_fetching(self, job, db):
        """targets == [] → 跳过，且**不触发任何抓取**（与「全量回填」严格区分）"""
        db.add(Fund(fund_code='000001', name='基金A'))
        db.commit()

        result = job.run(full_sync=False, targets=[])
        assert result['status'] == 'success'
        assert result['stats']['total'] == 0
        job.adapter.fetch_fund_manager.assert_not_called()

    def test_explicit_targets_ignore_other_funds_in_db(self, job, db):
        """显式 targets → 只处理目标基金，不被库内其他基金带偏"""
        db.add_all([Fund(fund_code='000001', name='基金A'), Fund(fund_code='000002', name='基金B')])
        db.commit()
        job.adapter.fetch_fund_manager.return_value = []

        job.run(full_sync=False, targets=['000001'])
        called = [call.args[0] for call in job.adapter.fetch_fund_manager.call_args_list]
        assert called == ['000001']

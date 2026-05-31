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

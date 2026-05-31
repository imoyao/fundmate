# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 12:51
# File : test_fund_manager_job.py
# -*- coding: utf-8 -*-
"""测试 FundManagerSyncJob"""

from unittest.mock import MagicMock

import pytest

from app.domains.funds.models import Fund, Manager
from app.services.sync.jobs.fund_manager_job import FundManagerSyncJob


class TestFundManagerSyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        return FundManagerSyncJob(adapter, db)

    def test_run_integration(self, job, db):
        db.add(Fund(fund_code='000001', name='测试基金'))
        db.commit()

        job.adapter.fetch_fund_manager.return_value = [
            {'name': '张三', 'mgr_code': 'MGR001', 'appointment_date': None},
            {'name': '李四', 'mgr_code': 'MGR002', 'appointment_date': None},
        ]

        result = job.run(full_sync=True)
        assert result['status'] == 'success'
        assert result['stats']['success'] == 2

        mgrs = db.query(Manager).all()
        assert len(mgrs) == 2

        # 第二次运行：新建 job 实例
        job2 = FundManagerSyncJob(job.adapter, db)
        job2.adapter.fetch_fund_manager.return_value = [
            {'name': '张三', 'mgr_code': 'MGR001', 'appointment_date': None},
            {'name': '李四', 'mgr_code': 'MGR002', 'appointment_date': None},
        ]
        result2 = job2.run(full_sync=True)
        assert result2['stats']['success'] == 0

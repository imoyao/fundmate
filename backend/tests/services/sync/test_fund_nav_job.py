# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 12:50
# File : test_fund_nav_job.py
# -*- coding: utf-8 -*-
"""测试 FundNavSyncJob 的数据清洗、去重及运行"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.domains.funds.models import DailyWorth, Fund
from app.services.sync.jobs.fund_nav_job import FundNavSyncJob


class TestFundNavSyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        adapter.get_name.return_value = 'mock_xalpha'
        return FundNavSyncJob(adapter, db)

    # ── _validate_data ──────────────────────────────

    def test_validate_normal_records(self, job):
        raw = [
            {'fund_code': '000001', 'date': date(2025, 1, 2), 'unit_nav': 1.234, 'acc_nav': 2.345},
            {'fund_code': '000002', 'date': date(2025, 1, 2), 'unit_nav': 0.987, 'acc_nav': 1.111},
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 2

    def test_validate_date_as_string(self, job):
        raw = [
            {'fund_code': '000001', 'date': '2025-01-03', 'unit_nav': 1.5},
            {'fund_code': '000001', 'date': 'not-a-date', 'unit_nav': 1.0},  # 非法日期
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert isinstance(validated[0]['date'], date)
        assert validated[0]['date'] == date(2025, 1, 3)

    def test_validate_missing_required(self, job):
        raw = [
            {'fund_code': '000001', 'unit_nav': 1.0},  # 缺 date
            {'date': date(2025, 1, 1), 'unit_nav': 1.0},  # 缺 fund_code
            {'fund_code': '000002', 'date': date(2025, 1, 2)},  # 缺 unit_nav
            {'fund_code': '000003', 'date': date(2025, 1, 3), 'unit_nav': 1.2},
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert validated[0]['fund_code'] == '000003'

    # ── _deduplicate (复合键) ──────────────────────

    def test_deduplicate_all_new(self, job, db):
        data = [
            {'fund_code': '000001', 'date': date(2025, 1, 1), 'unit_nav': 1.0},
            {'fund_code': '000002', 'date': date(2025, 1, 1), 'unit_nav': 2.0},
        ]
        new = job._deduplicate(data)
        assert len(new) == 2

    def test_deduplicate_existing_composite_key(self, job, db):
        # 插入一条已有记录
        db.add(DailyWorth(fund_code='000001', date=date(2025, 1, 1), unit_nav=1.0))
        db.commit()

        data = [
            {'fund_code': '000001', 'date': date(2025, 1, 1), 'unit_nav': 1.0},
            {'fund_code': '000001', 'date': date(2025, 1, 2), 'unit_nav': 1.1},
            {'fund_code': '000002', 'date': date(2025, 1, 1), 'unit_nav': 2.0},
        ]
        new = job._deduplicate(data)
        assert len(new) == 2

        # 这里定义 codes_and_dates
        codes_and_dates = {(item['fund_code'], item['date']) for item in new}
        assert ('000001', date(2025, 1, 1)) not in codes_and_dates
        assert ('000001', date(2025, 1, 2)) in codes_and_dates
        assert ('000002', date(2025, 1, 1)) in codes_and_dates

    # ── run 集成 ─────────────────────────────────

    def test_run_integration(self, job, db):
        db.add(Fund(fund_code='000001', name='测试基金'))
        db.commit()

        job.adapter.fetch_fund_nav.return_value = [
            {'fund_code': '000001', 'date': date(2025, 1, 1), 'unit_nav': 1.234, 'acc_nav': 2.345},
            {'fund_code': '000001', 'date': date(2025, 1, 2), 'unit_nav': 1.250, 'acc_nav': 2.400},
        ]

        result = job.run(full_sync=True)
        assert result['status'] == 'success'
        assert result['stats']['total'] == 2
        assert result['stats']['success'] == 2

        rows = db.query(DailyWorth).all()
        assert len(rows) == 2

        # 第二次运行：新建 job 实例
        job2 = FundNavSyncJob(job.adapter, db)
        job2.adapter.fetch_fund_nav.return_value = [
            {'fund_code': '000001', 'date': date(2025, 1, 1), 'unit_nav': 1.234},
        ]
        result2 = job2.run(full_sync=True)
        assert result2['stats']['success'] == 0

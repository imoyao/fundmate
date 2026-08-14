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

    def test_validate_normal_records(self, job):
        """正常净值数据通过校验"""
        raw = [
            {'fund_code': '000001', 'date': date(2025, 1, 2), 'unit_nav': 1.234, 'acc_nav': 2.345},
            {'fund_code': '000002', 'date': date(2025, 1, 2), 'unit_nav': 0.987, 'acc_nav': 1.111},
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 2

    def test_validate_date_as_string(self, job):
        """日期字符串应被正确转换为 date 对象"""
        raw = [
            {'fund_code': '000001', 'date': '2025-01-03', 'unit_nav': 1.5},
            {'fund_code': '000001', 'date': 'not-a-date', 'unit_nav': 1.0},
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert isinstance(validated[0]['date'], date)

    def test_validate_missing_required(self, job):
        """缺失必填字段的记录应被过滤"""
        raw = [
            {'fund_code': '000001', 'unit_nav': 1.0},
            {'date': date(2025, 1, 1), 'unit_nav': 1.0},
            {'fund_code': '000003', 'date': date(2025, 1, 3), 'unit_nav': 1.2},
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert validated[0]['fund_code'] == '000003'

    def test_deduplicate_existing_composite_key(self, job, db):
        """基于复合键 (fund_code, date) 去重"""
        # 外键约束：DailyWorth.fund_code 引用 funds.fund_code，须先建父记录
        fund = db.query(Fund).filter_by(fund_code='000001').first()
        if not fund:
            fund = Fund(fund_code='000001', name='测试基金')
            db.add(fund)
            db.flush()

        db.add(DailyWorth(fund_code='000001', date=date(2025, 1, 1), unit_nav=1.0))
        db.commit()

        data = [
            {'fund_code': '000001', 'date': date(2025, 1, 1), 'unit_nav': 1.0},
            {'fund_code': '000001', 'date': date(2025, 1, 2), 'unit_nav': 1.1},
            {'fund_code': '000002', 'date': date(2025, 1, 1), 'unit_nav': 2.0},
        ]
        new = job._deduplicate(data)
        assert len(new) == 2

        codes_and_dates = {(item['fund_code'], item['date']) for item in new}
        assert ('000001', date(2025, 1, 1)) not in codes_and_dates
        assert ('000001', date(2025, 1, 2)) in codes_and_dates

    def test_run_integration(self, job, db):
        """端到端测试：全量同步写入净值数据"""
        fund = Fund(fund_code='000001', name='测试基金')
        db.add(fund)
        db.commit()

        job.adapter.fetch_fund_nav.return_value = [
            {'fund_code': '000001', 'date': date(2025, 1, 1), 'unit_nav': 1.234, 'acc_nav': 2.345},
            {'fund_code': '000001', 'date': date(2025, 1, 2), 'unit_nav': 1.250, 'acc_nav': 2.400},
        ]

        result = job.run(full_sync=True, targets=['000001'])
        assert result['status'] == 'success'
        assert result['stats']['total'] == 1
        assert result['stats']['success'] == 2

        rows = db.query(DailyWorth).all()
        assert len(rows) == 2

    def test_run_allows_empty_data(self, job, db):
        """无目标代码时允许空数据返回，不报错"""
        result = job.run(full_sync=False, targets=[])
        assert result['status'] == 'success'

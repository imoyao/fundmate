# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 12:30
# File : test_jobs.py
# -*- coding: utf-8 -*-
"""测试各个 SyncJob 的 validate / deduplicate"""

from unittest.mock import MagicMock

import pytest

from app.domains.funds.models import Fund
from app.domains.securities.models import Security
from app.services.sync.jobs.fund_list_job import FundListSyncJob
from app.services.sync.jobs.stock_list_job import StockListSyncJob


class TestStockListSyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        return StockListSyncJob(adapter, db)

    def test_validate_normal(self, job):
        raw = [
            {'symbol': 'SH600519', 'name': '茅台'},
            {'symbol': 'SZ000001', 'name': '平安'},
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 2
        for item in validated:
            assert item['market'] == 'CN_A'
            assert item['type'] == 'stock'

    def test_validate_missing_symbol(self, job):
        raw = [{'name': '无代码'}, {'symbol': 'SH600519', 'name': '茅台'}]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert validated[0]['symbol'] == 'SH600519'

    def test_deduplicate_all_new(self, job, db):
        data = [{'symbol': 'SH600519', 'name': '茅台'}, {'symbol': 'SZ000001', 'name': '平安'}]
        new = job._deduplicate(data)
        assert len(new) == 2

    def test_deduplicate_existing(self, job, db):
        db.add(Security(symbol='SH600519', name='茅台', market='CN_A', type='stock'))
        db.commit()
        data = [{'symbol': 'SH600519', 'name': '茅台'}, {'symbol': 'SZ000001', 'name': '平安'}]
        new = job._deduplicate(data)
        assert len(new) == 1
        assert new[0]['symbol'] == 'SZ000001'


class TestFundListSyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        return FundListSyncJob(adapter, db)

    def test_validate_normal(self, job):
        raw = [{'fund_code': '000001', 'name': '基金A'}, {'fund_code': '000002', 'name': '基金B'}]
        validated = job._validate_data(raw)
        assert len(validated) == 2

    def test_validate_invalid_code(self, job):
        raw = [{'fund_code': 'abc', 'name': '无效'}, {'fund_code': '000001', 'name': '有效'}]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert validated[0]['fund_code'] == '000001'

    def test_deduplicate(self, job, db):
        db.add(Fund(fund_code='000001', name='基金A'))
        db.commit()
        data = [{'fund_code': '000001', 'name': '基金A'}, {'fund_code': '000002', 'name': '基金B'}]
        new = job._deduplicate(data)
        assert len(new) == 1
        assert new[0]['fund_code'] == '000002'

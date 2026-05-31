# -*- coding: utf-8 -*-
"""测试 StockListSyncJob 和 FundListSyncJob 的校验与去重逻辑"""

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
        """正常数据清洗：补充默认值"""
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
        """缺失 symbol 的记录应被过滤"""
        raw = [{'name': '无代码'}, {'symbol': 'SH600519', 'name': '茅台'}]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert validated[0]['symbol'] == 'SH600519'

    def test_deduplicate_all_new(self, job, db):
        """全部为新数据时，不去除任何记录"""
        data = [
            {'symbol': 'SH600519', 'name': '茅台'},
            {'symbol': 'SZ000001', 'name': '平安'},
        ]
        new = job._deduplicate(data)
        assert len(new) == 2

    def test_deduplicate_existing(self, job, db):
        """已存在的 symbol 应被去重"""
        sec = Security(symbol='SH600519', name='茅台', market='CN_A', type='stock')
        db.add(sec)
        db.commit()

        data = [
            {'symbol': 'SH600519', 'name': '茅台'},
            {'symbol': 'SZ000001', 'name': '平安'},
        ]
        new = job._deduplicate(data)
        assert len(new) == 1
        assert new[0]['symbol'] == 'SZ000001'


class TestFundListSyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        return FundListSyncJob(adapter, db)

    def test_validate_normal(self, job):
        """正常的基金代码和名称应通过校验"""
        raw = [
            {'fund_code': '000001', 'name': '基金A'},
            {'fund_code': '000002', 'name': '基金B'},
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 2

    def test_validate_invalid_code(self, job):
        """非 6 位数字的基金代码应被过滤"""
        raw = [
            {'fund_code': 'abc', 'name': '无效'},
            {'fund_code': '000001', 'name': '有效'},
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert validated[0]['fund_code'] == '000001'

    def test_deduplicate(self, job, db):
        """已存在的 fund_code 应被去重"""
        fund = Fund(fund_code='000001', name='基金A')
        db.add(fund)
        db.commit()

        data = [
            {'fund_code': '000001', 'name': '基金A'},
            {'fund_code': '000002', 'name': '基金B'},
        ]
        new = job._deduplicate(data)
        assert len(new) == 1
        assert new[0]['fund_code'] == '000002'

    def test_run_without_targets_triggers_full_sync(self, job, db):
        """未传入 targets 时，Job 应自行获取全量数据"""
        # FundListSyncJob 内部调用的是 fetch_fund_list，而不是 fetch_stock_list
        job.adapter.fetch_fund_list.return_value = [
            {'fund_code': '000001', 'name': '基金A'},
            {'fund_code': '000002', 'name': '基金B'},
        ]
        result = job.run(full_sync=True)
        assert result['status'] == 'success'
        assert result['stats']['total'] == 2
        assert result['stats']['success'] == 2

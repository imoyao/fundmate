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
        """存量 symbol **保留**在结果里，交给 `_save_data` 做 upsert 更新（#1104）。

        原先此处会过滤掉已存在的 symbol（`_deduplicate_by_unique_key`），于是
        「ETF / 可转债被硬编码成 type='stock'」这类存量记录永远修不回来——
        名录补齐后日线取数仍按错误 type 分派接口。去重现在只负责**本次抓取内部**的重复。
        """
        sec = Security(symbol='SH600519', name='茅台', market='CN_A', type='stock')
        db.add(sec)
        db.commit()

        data = [
            {'symbol': 'SH600519', 'name': '茅台'},
            {'symbol': 'SZ000001', 'name': '平安'},
        ]
        new = job._deduplicate(data)
        assert [item['symbol'] for item in new] == ['SH600519', 'SZ000001']

    def test_deduplicate_within_batch(self, job, db):
        """本次抓取内部的重复 symbol 仍要去掉（否则 bulk_insert 会撞唯一键）"""
        data = [
            {'symbol': 'SH600519', 'name': '茅台'},
            {'symbol': 'SH600519', 'name': '茅台'},
            {'symbol': 'SZ000001', 'name': '平安'},
        ]
        new = job._deduplicate(data)
        assert [item['symbol'] for item in new] == ['SH600519', 'SZ000001']

    def test_save_data_updates_existing_type(self, job, db):
        """存量记录的 type / name 被 upsert 更新——ETF / 可转债 type 修正的关键路径（#1104）。"""
        db.add(Security(symbol='SZ159857', name='旧名', market='CN_A', type='stock'))
        db.commit()

        job._save_data(
            [
                {
                    'symbol': 'SZ159857',
                    'name': '通信ETF',
                    'market': 'CN_A',
                    'type': 'etf',
                    'currency': 'CNY',
                }
            ]
        )

        row = db.query(Security).filter(Security.symbol == 'SZ159857').one()
        assert row.type == 'etf'
        assert row.name == '通信ETF'


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

    def test_existing_fund_is_not_updated(self, job, db):
        """「只增不改」契约：已存在 fund_code 的字段变更**不会**被同步（#1402）。

        本测试锁定的正是「fund_list 不是全量刷新」这一事实。若将来真改成 upsert，
        本测试会失败——届时必须同步更新模块 docstring 与 #1402 的结论，而不是
        直接删断言。
        """
        db.add(Fund(fund_code='000001', name='旧名称'))
        db.commit()

        job.adapter.fetch_fund_list.return_value = [
            {'fund_code': '000001', 'name': '新名称'},
            {'fund_code': '000002', 'name': '基金B'},
        ]
        result = job.run(full_sync=True)
        assert result['status'] == 'success'
        assert result['stats']['total'] == 2
        assert result['stats']['success'] == 1  # 仅 000002 入库，000001 被跳过

        db.expire_all()
        assert db.query(Fund).filter_by(fund_code='000001').one().name == '旧名称'
        assert db.query(Fund).filter_by(fund_code='000002').one().name == '基金B'

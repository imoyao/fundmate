# -*- coding: utf-8 -*-
"""测试分批写入与断点续传"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.domains.funds.models import DailyWorth, Fund
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.sync.jobs.fund_nav_job import FundNavSyncJob
from app.services.sync.jobs.price_history_job import PriceHistorySyncJob


def _make_mock_price_data(symbol):
    """构造一只股票的两条行情记录"""
    return [
        {
            'symbol': symbol,
            'trade_date': date(2025, 1, 1),
            'open': 100,
            'high': 105,
            'low': 99,
            'close': 102,
            'volume': 1000,
            'adj_close': 102,
            'source': 'test',
        },
        {
            'symbol': symbol,
            'trade_date': date(2025, 1, 2),
            'open': 102,
            'high': 106,
            'low': 101,
            'close': 104,
            'volume': 1200,
            'adj_close': 104,
            'source': 'test',
        },
    ]


def _make_mock_nav_data(code):
    """构造一只基金的两条净值记录"""
    return [
        {'fund_code': code, 'date': date(2025, 1, 1), 'unit_nav': 1.0, 'acc_nav': 1.1},
        {'fund_code': code, 'date': date(2025, 1, 2), 'unit_nav': 1.02, 'acc_nav': 1.12},
    ]


class TestPriceHistoryBatch:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        adapter.get_name.return_value = 'mock_akshare'
        return PriceHistorySyncJob(adapter, db)

    @pytest.fixture
    def securities(self, db):
        secs = [
            Security(symbol='SH600000', name='股票0', market='CN_A', type='stock', currency='CNY'),
            Security(symbol='SH600001', name='股票1', market='CN_A', type='stock', currency='CNY'),
            Security(symbol='SH600002', name='股票2', market='CN_A', type='stock', currency='CNY'),
            Security(symbol='SH600003', name='股票3', market='CN_A', type='stock', currency='CNY'),
        ]
        db.add_all(secs)
        db.commit()
        return secs

    def test_batch_write_basic(self, job, db, securities):
        """全量分批写入所有数据"""
        job.adapter.fetch_stock_price.side_effect = lambda symbol, *a, **kw: _make_mock_price_data(symbol)
        job.batch_size = 2

        targets = [s.symbol for s in securities]
        result = job.run(full_sync=True, targets=targets)
        assert result['status'] == 'success'
        assert db.query(PriceHistory).count() == 8
        assert result['stats']['success'] == 8

    def test_resume_after_interruption(self, job, db, securities):
        """断点续传：已存在的数据被跳过"""
        db.add(PriceHistory(security_id=securities[0].id, trade_date=date(2025, 1, 1), close=100))
        db.add(PriceHistory(security_id=securities[1].id, trade_date=date(2025, 1, 1), close=100))
        db.commit()

        job.adapter.fetch_stock_price.side_effect = lambda symbol, *a, **kw: _make_mock_price_data(symbol)
        job.batch_size = 2

        targets = [s.symbol for s in securities]
        result = job.run(full_sync=True, targets=targets)
        assert db.query(PriceHistory).count() == 8
        assert result['stats']['success'] == 6
        assert result['stats']['skipped'] == 2

    def test_single_failure_does_not_block_others(self, job, db, securities):
        """某只股票失败不影响同批次其他股票"""

        def failing_fetch(symbol, *a, **kw):
            if symbol == 'SH600001':
                raise Exception('网络错误')
            return _make_mock_price_data(symbol)

        job.adapter.fetch_stock_price.side_effect = failing_fetch
        job.batch_size = 2

        targets = [s.symbol for s in securities]
        result = job.run(full_sync=True, targets=targets)
        assert db.query(PriceHistory).count() == 6
        assert result['stats']['success'] == 6

    def test_batch_logging(self, job, db, securities, capsys):
        """验证分批进度日志输出"""
        import sys

        from loguru import logger

        logger.remove()
        logger.add(sys.stderr, level='DEBUG')

        job.adapter.fetch_stock_price.side_effect = lambda symbol, *a, **kw: _make_mock_price_data(symbol)
        job.batch_size = 2

        targets = [s.symbol for s in securities]
        job.run(full_sync=True, targets=targets)

        captured = capsys.readouterr().err
        assert '进度: 2/4' in captured
        assert '进度: 4/4' in captured


class TestFundNavBatch:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        adapter.get_name.return_value = 'mock_xalpha'
        return FundNavSyncJob(adapter, db)

    @pytest.fixture
    def funds(self, db):
        fund_list = [Fund(fund_code=f'00000{i+1}', name=f'基金{i+1}') for i in range(4)]
        db.add_all(fund_list)
        db.commit()
        return fund_list

    def test_batch_write_basic(self, job, db, funds):
        """全量分批写入所有净值数据"""
        job.adapter.fetch_fund_nav.side_effect = lambda code, *a, **kw: _make_mock_nav_data(code)
        job.batch_size = 2

        targets = [f.fund_code for f in funds]
        result = job.run(full_sync=True, targets=targets)
        assert result['status'] == 'success'
        assert db.query(DailyWorth).count() == 8
        assert result['stats']['success'] == 8

    def test_resume(self, job, db, funds):
        """断点续传：已存在的净值被跳过"""
        db.add(DailyWorth(fund_code='000001', date=date(2025, 1, 1), unit_nav=1.0))
        db.add(DailyWorth(fund_code='000001', date=date(2025, 1, 2), unit_nav=1.02))
        db.commit()

        job.adapter.fetch_fund_nav.side_effect = lambda code, *a, **kw: _make_mock_nav_data(code)
        job.batch_size = 2

        targets = [f.fund_code for f in funds]
        result = job.run(full_sync=True, targets=targets)
        assert db.query(DailyWorth).count() == 8
        assert result['stats']['success'] == 6
        assert result['stats']['skipped'] == 2

    def test_single_failure(self, job, db, funds):
        """某只基金失败不影响同批次其他基金"""

        def failing(code, *args, **kwargs):
            if code == '000002':
                raise Exception('接口错误')
            return _make_mock_nav_data(code)

        job.adapter.fetch_fund_nav.side_effect = failing
        job.batch_size = 2

        targets = [f.fund_code for f in funds]
        result = job.run(full_sync=True, targets=targets)
        assert db.query(DailyWorth).count() == 6
        assert result['stats']['success'] == 6

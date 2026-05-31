# tests/services/sync/test_batch_jobs.py

from datetime import date
from unittest.mock import MagicMock

import pytest
from loguru import logger

from app.domains.funds.models import DailyWorth, Fund
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.sync.jobs.fund_nav_job import FundNavSyncJob
from app.services.sync.jobs.price_history_job import PriceHistorySyncJob

logger.remove()
logger.add(lambda msg: None, level='DEBUG')  # 将日志发送到 stderr，pytest 的 capsys 可捕获


# ── 辅助函数 ──
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


# ── PriceHistorySyncJob 测试 ──
class TestPriceHistoryBatch:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        adapter.get_name.return_value = 'mock_akshare'
        return PriceHistorySyncJob(adapter, db)

    @pytest.fixture
    def securities(self, db):
        secs = [
            Security(symbol=f'SH600{i:03d}', name=f'股票{i}', market='CN_A', type='stock', currency='CNY')
            for i in range(4)
        ]
        db.add_all(secs)
        db.commit()
        return secs

    def test_batch_write_basic(self, job, db, securities):
        """全量分批写入所有数据"""

        # mock fetch_stock_price 返回两条行情
        def mock_fetch(symbol, *args, **kwargs):
            return _make_mock_price_data(symbol)

        job.adapter.fetch_stock_price.side_effect = mock_fetch

        job.batch_size = 2
        result = job.run(full_sync=True)

        assert result['status'] == 'success'
        # 4 只股票 × 2 条 = 8 条
        assert db.query(PriceHistory).count() == 8
        assert result['stats']['success'] == 8
        assert result['stats']['total'] == 8

    def test_resume_after_interruption(self, job, db, securities):
        """断点续传：已有部分数据时，只写入缺失数据"""
        # 先插入前两只股票的部分行情（模拟中断）
        db.add(PriceHistory(security_id=securities[0].id, trade_date=date(2025, 1, 1), close=100))
        db.add(PriceHistory(security_id=securities[1].id, trade_date=date(2025, 1, 1), close=100))
        db.commit()

        job.adapter.fetch_stock_price.side_effect = lambda s: _make_mock_price_data(s)  # noqa: E731
        job.batch_size = 2
        result = job.run(full_sync=True)

        # 总共应有 8 条（已有的 2 条 + 新写入的 6 条）
        assert db.query(PriceHistory).count() == 8
        assert result['stats']['success'] == 6  # 新写入 6 条
        # 跳过数应等于已存在的记录数（去重统计）
        assert result['stats']['skipped'] == 2

    def test_single_failure_does_not_block_others(self, job, db, securities):
        """某只股票失败不影响同批次其他股票"""
        original_mock = lambda s: _make_mock_price_data(s)  # noqa: E731

        def failing_fetch(symbol, *args, **kwargs):
            if symbol == 'SH600001':
                raise Exception('网络错误')
            return original_mock(symbol)

        job.adapter.fetch_stock_price.side_effect = failing_fetch

        job.batch_size = 2
        result = job.run(full_sync=True)

        # 4 只股票，其中 1 只失败 → 3 × 2 = 6 条
        assert db.query(PriceHistory).count() == 6
        assert result['stats']['success'] == 6
        # errors 列表中应有失败信息
        assert len(result['stats'].get('errors', [])) == 1

    def test_batch_logging(self, job, db, securities, capsys):
        # 强制 loguru 输出到 stderr，以便 capsys 捕获
        import sys

        from loguru import logger

        logger.remove()
        logger.add(sys.stderr, level='DEBUG')

        job.adapter.fetch_stock_price.side_effect = lambda s: _make_mock_price_data(s)  # noqa: E731
        job.batch_size = 2
        job.run(full_sync=True)

        captured = capsys.readouterr().err
        assert '全量进度: 批次 1/2' in captured, f'日志内容: {captured[:500]}'
        assert '全量进度: 批次 2/2' in captured


# ── FundNavSyncJob 测试 ──
class TestFundNavBatch:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        adapter.get_name.return_value = 'mock_xalpha'
        return FundNavSyncJob(adapter, db)

    @pytest.fixture
    def funds(self, db):
        funds = [Fund(fund_code=f'00000{i + 1}', name=f'基金{i + 1}') for i in range(4)]
        db.add_all(funds)
        db.commit()
        return funds

    def test_batch_write_basic(self, job, db, funds):
        job.adapter.fetch_fund_nav.side_effect = lambda c, *a, **kw: _make_mock_nav_data(c)  # noqa: E731
        job.batch_size = 2
        result = job.run(full_sync=True)

        assert result['status'] == 'success'
        assert db.query(DailyWorth).count() == 8
        assert result['stats']['success'] == 8

    def test_resume(self, job, db, funds):
        # 预存 2 条记录
        db.add(DailyWorth(fund_code='000001', date=date(2025, 1, 1), unit_nav=1.0))
        db.add(DailyWorth(fund_code='000001', date=date(2025, 1, 2), unit_nav=1.02))
        db.commit()

        job.adapter.fetch_fund_nav.side_effect = lambda c, *a, **kw: _make_mock_nav_data(c)  # noqa: E731
        job.batch_size = 2
        result = job.run(full_sync=True)

        assert db.query(DailyWorth).count() == 8
        assert result['stats']['success'] == 6
        assert result['stats']['skipped'] == 2

    def test_single_failure(self, job, db, funds):
        original = lambda c: _make_mock_nav_data(c)  # noqa: E731

        def failing(code, *args, **kwargs):
            if code == '000002':
                raise Exception('接口错误')
            return original(code)

        job.adapter.fetch_fund_nav.side_effect = failing

        job.batch_size = 2
        result = job.run(full_sync=True)

        assert db.query(DailyWorth).count() == 6
        assert result['stats']['success'] == 6
        # 确保 errors 列表包含失败信息
        assert len(result['stats'].get('errors', [])) == 1
        assert result['stats']['errors'][0]['fund_code'] == '000002'

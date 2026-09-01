# backend/tests/services/sync/test_dividend_split_job.py
"""#1179 回归：分红/送股抓取 Job 的转换与去重逻辑。"""

from datetime import date
from decimal import Decimal

from app.services.sync.jobs.dividend_split_job import DividendSplitSyncJob


class _FakeAdapter:
    def fetch_stock_dividend(self, symbol):
        return [
            {
                'symbol': symbol,
                'ex_date': date(2024, 6, 1),
                'bonus_ratio': 5.0,
                'transfer_ratio': 0.0,
                'cash_ratio': 2.0,
                'desc': '10送5派2',
            }
        ]

    def fetch_fund_dividend(self, symbol):
        return [
            {
                'symbol': symbol,
                'ann_date': date(2024, 6, 1),
                'ann_title': '收益分配公告',
            }
        ]


def _make_job(db):
    job = DividendSplitSyncJob(_FakeAdapter(), db)
    job._holding_shares = lambda s: Decimal('1000')
    return job


def test_split_record_conversion(db):
    job = _make_job(db)
    rec = job._event_to_record(
        {
            'symbol': 'SH600000',
            'ex_date': date(2024, 6, 1),
            'bonus_ratio': 5.0,
            'transfer_ratio': 0.0,
            'cash_ratio': 2.0,
            'desc': '10送5派2',
        }
    )
    assert rec is not None
    assert rec.business_type == 'split'
    assert rec.shares == Decimal('500')  # 1000 * 5 / 10
    assert rec.amount == Decimal('0')


def test_dividend_record_conversion(db):
    job = _make_job(db)
    rec = job._event_to_record(
        {
            'symbol': 'SH600000',
            'ex_date': date(2024, 6, 1),
            'bonus_ratio': 0.0,
            'transfer_ratio': 0.0,
            'cash_ratio': 2.0,
            'desc': '10派2',
        }
    )
    assert rec.business_type == 'dividend'
    assert rec.shares == Decimal('0')
    assert rec.amount == Decimal('200')  # 1000 * 2 / 10


def test_deduplicate_by_import_hash(db):
    job = _make_job(db)
    rec = job._event_to_record(
        {
            'symbol': 'SH600000',
            'ex_date': date(2024, 6, 1),
            'bonus_ratio': 0.0,
            'transfer_ratio': 0.0,
            'cash_ratio': 2.0,
            'desc': '10派2',
        }
    )
    unique = job._deduplicate([rec, rec])
    assert len(unique) == 1

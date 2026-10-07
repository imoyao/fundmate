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


# ── #1833：持仓查询失败不得写成 0 金额流水 ──────────────────────────────────


def test_holding_query_failure_skips_event_instead_of_zero_amount(db):
    """持仓查询失败 → 跳过该事件，**不落库**。

    早先实现是`except: return Decimal('0')`，于是持仓一查不到就写出 amount=0 的
    分红流水；而 `_deduplicate` 靠 import_hash 去重，下一轮会把这条 0 金额记录当
    重复跳过 —— **永久不可自愈**，用户账上多一条 0 元分红。
    """
    job = DividendSplitSyncJob(_FakeAdapter(), db)

    # 造一个查询必炸的 session
    class _Boom:
        def query(self, *_a, **_k):
            raise RuntimeError('db down')

        def add(self, *_a, **_k):
            pass

    job.db = _Boom()
    job.stats = {}
    assert job._holding_shares('SH600000') is None
    # 该失败必须进 errors，否则与「确实没持仓」同形
    assert any(e.get('stage') == 'holding_query' for e in job.stats['errors'])

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
    assert rec is None, '持仓查询失败时必须跳过事件，不能落 0 金额流水'


def test_zero_holding_is_still_a_valid_record(db):
    """反向：确实持有 0 股**不是**查询失败，事件照常落库（0 是合法结果）。"""
    job = DividendSplitSyncJob(_FakeAdapter(), db)
    job.stats = {}
    job._holding_shares = lambda s: Decimal('0')
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
    assert rec is not None
    assert rec.amount == Decimal('0')
    assert job.stats.get('errors', []) == []

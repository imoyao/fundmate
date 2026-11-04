# -*- coding: utf-8 -*-
"""#2720：交易流水 CSV 导出排序 + 清仓「特别关注」条件判定（下沉后的回归网）。

覆盖两处**曾经出错、且没有测试能发现**的口径：
1. 导出按「有效交易日」正序 —— trade_date 缺失的历史导入行不能整批沉底/置顶；
2. 持有天数在 trade_date 整列缺失时回退 confirm_date，且一侧全缺时**不抛异常**
   （旧实现对空序列 `min()` 直接 ValueError → 端点 500）。
"""

from datetime import date, datetime

from app.domains.transactions.models import Transaction
from app.services.transaction_service import build_transactions_csv
from app.services.watchlist_service import smart_prompt_conditions


def _txn(db, *, trade_date=None, confirm_date=None, symbol='000001', txn_type='buy'):
    txn = Transaction(
        family_id=1,
        symbol=symbol,
        txn_type=txn_type,
        trade_date=trade_date,
        confirm_date=confirm_date,
        quantity=10000,
        price=10000,
        amount=10000,
        fee=0,
        position_name='测试标的',
        asset_type='fund',
        status='success',
    )
    db.add(txn)
    db.flush()
    return txn


def _rows(csv_text):
    """CSV 文本 → 数据行（去掉表头），按逗号切列。"""
    lines = csv_text.strip().split('\n')
    return [line.split(',') for line in lines[1:]]


def test_export_orders_by_effective_day_asc(db):
    """只有确认日的行按确认日参与排序，而不是被 NULL 甩到两端。"""
    _txn(db, confirm_date=date(2026, 1, 5), symbol='AAA')  # 有效日 01-05 → 最前
    _txn(db, trade_date=datetime(2026, 2, 1, 10, 0), confirm_date=date(2026, 2, 3), symbol='BBB')
    _txn(db, confirm_date=date(2026, 3, 1), symbol='CCC')  # 有效日 03-01 → 最后

    rows = _rows(build_transactions_csv(db, 1))
    assert [row[3] for row in rows] == ['AAA', 'BBB', 'CCC']


def test_export_date_cell_stays_empty_when_missing(db):
    """缺 trade_date 时单元格留空，不冒充成确认日（兜底只用于排序）。"""
    _txn(db, confirm_date=date(2026, 1, 5))

    rows = _rows(build_transactions_csv(db, 1))
    assert rows[0][0] == ''  # 交易日期
    assert rows[0][1] == '2026-01-05'  # 确认日期


class _Item:
    def __init__(self, notes=None):
        self.notes = notes


class _TxnStub:
    def __init__(self, txn_type, trade_date=None, confirm_date=None):
        self.txn_type = txn_type
        self.trade_date = trade_date
        self.confirm_date = confirm_date


def test_smart_prompt_falls_back_to_confirm_date():
    """两侧都缺 trade_date 时用 confirm_date 算持有天数（2026-01-01 → 2026-08-01 = 212 天）。"""
    txns = [
        _TxnStub('buy', confirm_date=date(2026, 1, 1)),
        _TxnStub('sell', confirm_date=date(2026, 8, 1)),
    ]

    conditions = smart_prompt_conditions(_Item(), txns)

    assert conditions['holding_days'] == 212
    assert conditions['holding_days_gt_180'] is True
    assert conditions['should_prompt'] is True


def test_smart_prompt_one_side_without_any_date_does_not_raise():
    """一侧日期全缺 → 持有天数按「算不出来」记 0，不得对空序列 min/max（旧实现 500）。"""
    txns = [_TxnStub('buy'), _TxnStub('sell', confirm_date=date(2026, 8, 1))]

    conditions = smart_prompt_conditions(_Item(notes='想清仓'), txns)

    assert conditions['holding_days'] == 0
    assert conditions['has_notes'] is True
    assert conditions['should_prompt'] is True


def test_smart_prompt_thresholds_are_reported_as_flags():
    """7 笔流水触发 trade_count_gt_6；纯观察（无买卖、无备注）不提示。"""
    busy = [_TxnStub('buy', confirm_date=date(2026, 1, 1)) for _ in range(4)]
    busy += [_TxnStub('sell', confirm_date=date(2026, 2, 1)) for _ in range(3)]
    assert smart_prompt_conditions(_Item(), busy)['should_prompt'] is True
    assert smart_prompt_conditions(_Item(), busy)['trade_count_gt_6'] is True
    assert smart_prompt_conditions(_Item(), [])['should_prompt'] is False

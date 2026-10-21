# -*- coding: utf-8 -*-
"""#2136 行为测试：账户现金（major_category='cash'）必须真被读出来。

旧代码三处查询按 `major_category == 'current'` 过滤，而写入侧写的是 `'cash'`
⇒ 账户现金恒读成 0。本文件用**行为**钉住它：造一条 cash 资产，三个读出口
必须都看得到这笔钱；把大类换成词表外的值则**不应**被计入。

这条测试本身就是反向探针：把读侧改回 'current'，下面三条断言立即转红。
"""

import pytest

from app.core.asset_types import MAJOR_CATEGORY_CASH
from app.services.ledger_service import LedgerService


@pytest.fixture
def cash_ledger(db):
    """一个账户 + 一笔 12,345.67 元的流动资金。"""
    from app.domains.ledgers.models import Ledger

    ledger = Ledger(name='活期账户', ledger_type='bank', family_id=1)
    db.add(ledger)
    db.commit()
    db.refresh(ledger)
    return ledger


def _add_asset(db, ledger, major_category, amount_yuan=12345.67, name='活期余额'):
    from app.domains.assets.models import Asset

    asset = Asset(
        name=name,
        major_category=major_category,
        amount=int(round(amount_yuan * 100)),
        ledger_id=ledger.id,
        family_id=1,
    )
    db.add(asset)
    db.commit()
    return asset


def test_bank_stats_reads_cash_asset(db, cash_ledger):
    """账户总览的活期余额必须等于那笔 cash 资产。"""
    _add_asset(db, cash_ledger, MAJOR_CATEGORY_CASH)

    stats = LedgerService.get_bank_stats(db, cash_ledger.id)

    assert stats['current_balance'] == pytest.approx(12345.67)
    assert stats['cash_balance'] == pytest.approx(12345.67)
    assert stats['total_market_value'] == pytest.approx(12345.67)


def test_cash_like_stats_counts_cash_asset(db, cash_ledger):
    """类现金合计必须把账户现金算进去（否则「账外类现金」少一块）。"""
    _add_asset(db, cash_ledger, MAJOR_CATEGORY_CASH)

    stats = LedgerService.get_cash_like_stats(db, cash_ledger.id, 1)

    assert stats['cash_amount'] == pytest.approx(12345.67)
    assert stats['cash_like_amount'] == pytest.approx(12345.67)


def test_cash_balance_reads_linked_cash_ledger(db, cash_ledger):
    """关联现金账户的活期余额（`get_cash_balance`）同样必须读得到。"""
    from app.domains.ledgers.models import Ledger

    linked = Ledger(name='资金池', ledger_type='bank', family_id=1)
    db.add(linked)
    db.commit()
    db.refresh(linked)
    cash_ledger.linked_cash_ledger_id = linked.id
    db.commit()
    _add_asset(db, linked, MAJOR_CATEGORY_CASH)

    assert LedgerService.get_cash_balance(db, cash_ledger) == pytest.approx(12345.67)


def test_off_vocabulary_category_is_not_counted(db, cash_ledger):
    """词表外的取值不得被计入账户现金（写侧已拒，这里是读侧的兜底语义）。"""
    _add_asset(db, cash_ledger, 'current', name='历史错值')

    stats = LedgerService.get_bank_stats(db, cash_ledger.id)

    assert stats['current_balance'] == pytest.approx(0.0)

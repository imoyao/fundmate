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


def _add_position(db, ledger, symbol='021180', quantity=1000.0, avg_price=2.0, current_price=2.5):
    from app.core.money import Money
    from app.domains.positions.models import Position

    pos = Position(
        symbol=symbol,
        name='测试混合C',
        ledger_id=ledger.id,
        quantity=Money.shares_to_min_unit(quantity),
        avg_price=Money.yuan_to_price_units(avg_price),
        current_price=Money.yuan_to_price_units(current_price),
        ownership_status='active',
        source='manual',
        family_id=1,
    )
    db.add(pos)
    db.commit()
    return pos


# ── 银行账户的持仓盈亏（2026-10-28）────────────────────────────────────────
# 背景：`attach_ledger_summary` 的 bank 分支曾把 `pnl` 写死 0.0（注释「bank 不直接显示盈亏」）。
# 但银行账户本来就可能持有基金（微众银行：现金 + 自购基金同账户；本地库实测 ledger 3 有
# 416 条流水，其中 bond 251 / money_fund 164 / fund 1）。把导入产生的幽灵基金账户合并回
# 银行账户后，若不补这一项，用户看到的「持仓盈亏 -3,384.98」会凭空消失，像是合并把数据弄丢了。


def test_bank_stats_reports_position_pnl(db, cash_ledger):
    """银行账户持有基金时，统计要给出持仓盈亏（现价口径，与总资产同源）。"""
    _add_position(db, cash_ledger)

    stats = LedgerService.get_bank_stats(db, cash_ledger.id)

    assert stats['position_pnl'] == pytest.approx(500.0)  # 1000 份 ×(2.5 − 2.0)
    assert stats['total_market_value'] == pytest.approx(2500.0)


def test_bank_summary_reports_pnl(db, cash_ledger):
    """账户卡摘要不得再把 bank 的盈亏压成 0。"""
    _add_position(db, cash_ledger)
    item = {'total_market_value': 0.0, 'pnl': 0.0, 'position_count': 0}

    LedgerService.attach_ledger_summary(db, cash_ledger, item)

    assert item['pnl'] == pytest.approx(500.0)
    assert item['position_count'] == 1


def test_bank_summary_pnl_is_zero_without_positions(db, cash_ledger):
    """防过宽：没有持仓的银行账户仍报 0，不该出现凭空的盈亏。"""
    item = {'total_market_value': 0.0, 'pnl': 0.0, 'position_count': 0}

    LedgerService.attach_ledger_summary(db, cash_ledger, item)

    assert item['pnl'] == 0.0
    assert item['position_count'] == 0

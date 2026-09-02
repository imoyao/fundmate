# -*- coding: utf-8 -*-
"""按占比批量更新总价单测（P1-4）。

覆盖：
- 正常按比例分摊，Σ(分配) == 总价
- 尾差归占比最大一笔
- 分母为 0（各账户市值均为 0）报错
- 无活跃持仓报错
- ledger_id 过滤只分摊到单账户
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.constants import ValuationMode
from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.services.value_allocation_service import allocate_value


def _make_balance(db, symbol, account_name, override_yuan, family_id=1):
    ledger = db.query(Ledger).filter_by(name=account_name, family_id=family_id).first()
    if not ledger:
        ledger = Ledger(name=account_name, ledger_type='bank', family_id=family_id)
        db.add(ledger)
        db.flush()
    pos = Position(
        symbol=symbol,
        name='投顾组合',
        market='CN_A',
        asset_type='fund',
        account_name=account_name,
        ledger_id=ledger.id,
        family_id=family_id,
        quantity=0,
        avg_price=0,
        current_price=0,
        currency='CNY',
        valuation_mode=ValuationMode.BALANCE.value,
        market_value_override=Money.yuan_to_cents(override_yuan),
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)
    return pos


def test_allocate_pro_rata_basic(db):
    """60% / 40% 两账户，录入 1 万总价应分别落到 6000 / 4000。"""
    _make_balance(db, 'ADV1', '账户A', 6000.0)
    _make_balance(db, 'ADV1', '账户B', 4000.0)
    result = allocate_value(db, 1, 'ADV1', 10000.0)
    db.commit()

    yuan = [a['allocated_yuan'] for a in result['allocations']]
    assert round(sum(yuan), 2) == 10000.0

    by_ledger = {a['ledger_id']: a['allocated_yuan'] for a in result['allocations']}
    ledger_a = db.query(Ledger).filter_by(name='账户A').first().id
    ledger_b = db.query(Ledger).filter_by(name='账户B').first().id
    assert round(by_ledger[ledger_a], 2) == 6000.0
    assert round(by_ledger[ledger_b], 2) == 4000.0

    # 落库校验：market_value_override 已按分写入
    pos_a = db.query(Position).filter_by(id=result['allocations'][0]['position_id']).first()
    assert pos_a.market_value_override == Money.yuan_to_cents(6000.0)
    assert pos_a.value_override_at is not None


def test_allocate_tail_diff_to_largest(db):
    """三账户等权重（1/3），总价 100 元无法整除 → 尾差 1 分归首个最大占比。"""
    _make_balance(db, 'ADV', 'A', 100.0)
    _make_balance(db, 'ADV', 'B', 100.0)
    _make_balance(db, 'ADV', 'C', 100.0)
    total = 100.0
    result = allocate_value(db, 1, 'ADV', total)
    db.commit()

    total_cents = int((Decimal(str(total)) * 100).to_integral_value(rounding='ROUND_HALF_UP'))
    assert sum(a['allocated_cents'] for a in result['allocations']) == total_cents

    largest = max(result['allocations'], key=lambda a: a['allocated_cents'])
    assert largest['allocated_cents'] == 3334


def test_allocate_zero_denominator_raises(db):
    """各账户市值均为 0 → 无法按比例，报错而非静默给错数。"""
    _make_balance(db, 'ADV', 'A', 0.0)
    with pytest.raises(ValueError):
        allocate_value(db, 1, 'ADV', 1000.0)
    db.rollback()


def test_allocate_no_positions_raises(db):
    """无活跃持仓 → 报错。"""
    with pytest.raises(ValueError):
        allocate_value(db, 1, 'NOPE', 1000.0)


def test_allocate_ledger_filter(db):
    """ledger_id 过滤：只把总价全部分摊到指定账户。"""
    _make_balance(db, 'ADV', 'A', 6000.0)
    _make_balance(db, 'ADV', 'B', 4000.0)
    ledger_b = db.query(Ledger).filter_by(name='B').first().id
    result = allocate_value(db, 1, 'ADV', 1000.0, ledger_id=ledger_b)
    db.commit()

    assert len(result['allocations']) == 1
    assert result['allocations'][0]['ledger_id'] == ledger_b
    assert result['allocations'][0]['allocated_yuan'] == 1000.0


# ---------------------------------------------------------------------------
# 资金进出检测与「下一个开盘日」提示（#1217）
# ---------------------------------------------------------------------------
def test_no_hint_on_first_allocation(db):
    """首次录入市值：没有 value_override_at 基准，不应误报资金进出。"""
    _make_balance(db, 'CF1', 'A', 6000.0)
    result = allocate_value(db, 1, 'CF1', 10000.0)
    db.commit()

    assert result['cash_flow_detected'] is False
    assert result['next_trading_day'] is None


def test_hint_when_cash_flow_after_last_override(db, make_transaction):
    """上次录入市值之后发生申购 → 提示在下一个开盘日更新其他存量持仓。"""
    pos_a = _make_balance(db, 'CF2', 'A', 6000.0)
    allocate_value(db, 1, 'CF2', 12000.0, as_of=date(2026, 8, 1))  # 建立基准
    db.commit()

    make_transaction(
        position_id=pos_a.id,
        ledger_id=pos_a.ledger_id,
        txn_type='buy',
        quantity=100.0,
        price=10.0,
        amount=1000.0,
        confirm_date=date(2026, 8, 20),
        symbol='CF2',
    )
    db.commit()

    result = allocate_value(db, 1, 'CF2', 15000.0, as_of=date(2026, 8, 31))
    db.commit()

    assert result['cash_flow_detected'] is True
    assert result['next_trading_day'] is not None


def test_no_hint_when_cash_flow_before_baseline(db, make_transaction):
    """基准日**之前**的流水不算资金进出（分摊基数没有被它影响）。"""
    pos_a = _make_balance(db, 'CF3', 'A', 6000.0)
    allocate_value(db, 1, 'CF3', 12000.0, as_of=date(2026, 8, 1))
    db.commit()

    make_transaction(
        position_id=pos_a.id,
        ledger_id=pos_a.ledger_id,
        txn_type='buy',
        quantity=100.0,
        price=10.0,
        amount=1000.0,
        confirm_date=date(2026, 7, 20),
        symbol='CF3',
    )
    db.commit()

    result = allocate_value(db, 1, 'CF3', 15000.0, as_of=date(2026, 8, 31))
    db.commit()

    assert result['cash_flow_detected'] is False
    assert result['next_trading_day'] is None


def test_hint_next_trading_day_skips_adjusted_weekend(db, make_transaction):
    """提示的「下一个开盘日」必须跳过调休补班的周末（交易日历唯一出口）。"""
    from app.core.trading_calendar import is_trading_day

    pos_a = _make_balance(db, 'CF4', 'A', 6000.0)
    allocate_value(db, 1, 'CF4', 12000.0, as_of=date(2026, 9, 1))
    db.commit()

    make_transaction(
        position_id=pos_a.id,
        ledger_id=pos_a.ledger_id,
        txn_type='buy',
        quantity=100.0,
        price=10.0,
        amount=1000.0,
        confirm_date=date(2026, 10, 1),
        symbol='CF4',
    )
    db.commit()

    # as_of = 2026-10-09(周五)，下一个开盘日应跳过调休周六 10-10，落到 10-12(周一)
    result = allocate_value(db, 1, 'CF4', 15000.0, as_of=date(2026, 10, 9))
    db.commit()

    assert result['cash_flow_detected'] is True
    next_day = date.fromisoformat(result['next_trading_day'])
    assert next_day == date(2026, 10, 12)
    assert is_trading_day(next_day) is True

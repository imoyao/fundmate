# -*- coding: utf-8 -*-
"""裁决 kind 的白名单守卫（2026-11-16 真机事故的回归网）。

## 事故形态

后端用 `flask run --port 8000 --no-reload` 起在 11-15 14:04，而 `kind='recompute'`
（「按流水重算份额」）是当晚 21:03 的提交才进 `apply_decision` 的。前端 Vite 会自动热更，
于是新前端把 `{kind:'recompute', discrepancy_id, symbol, ledger_id}` 发给旧后端：旧代码的
`if/elif` 没有这个分支 ⇒ 落到 `else` → `_apply_increment`（`op_type` 缺省 `'buy'`）
⇒ 没有 quantity ⇒ 用户点「按流水重算份额」却收到「数量必须大于 0」。若 payload 恰好带了
quantity，它会**真的写进一笔买入**。

## 本文件钉两件事

1. 未知 kind 一律 `ValueError`，且**一个字节都不写库**（流水 / 持仓 / 审计都不动）；
2. 白名单不得误伤现有动作 —— `recompute` 是最近加的那一个，必须照常执行。
"""

from datetime import date, datetime

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.reconciliation.models import AdjustmentLog, ReconciliationDiscrepancy
from app.domains.transactions.models import Transaction
from app.services.reconciliation_service import apply_decision

_FAMILY = 1
_SYMBOL = 'SH600027'
_DAY = date(2026, 5, 1)


@pytest.fixture
def ledger(db):
    lg = Ledger(name='银河证券', ledger_type='stock', family_id=_FAMILY)
    db.add(lg)
    db.flush()
    return lg


def _position(db, ledger_id, shares=60):
    p = Position(
        symbol=_SYMBOL,
        name='华电国际',
        market='CN_A',
        asset_type='stock',
        ledger_id=ledger_id,
        family_id=_FAMILY,
        quantity=Money.shares_to_min_unit(shares),
        avg_price=Money.yuan_to_price_units(10),
        current_price=Money.yuan_to_price_units(10),
        source='manual',
        ownership_status='active',
    )
    db.add(p)
    db.flush()
    return p


def _txn(db, ledger_id, position, txn_type, shares, day=_DAY):
    t = Transaction(
        position_id=position.id,
        ledger_id=ledger_id,
        family_id=_FAMILY,
        symbol=_SYMBOL,
        txn_type=txn_type,
        quantity=Money.shares_to_min_unit(shares),
        price=Money.yuan_to_price_units(10),
        amount=Money.yuan_to_cents(shares * 10),
        confirm_date=day,
        trade_date=datetime.combine(day, datetime.min.time()),
        position_name='华电国际',
        account_name='银河证券',
        status='success',
        entry_status='success',
    )
    db.add(t)
    db.flush()
    return t


def _disc(db, ledger_id, *, expected, actual):
    d = ReconciliationDiscrepancy(
        family_id=_FAMILY,
        domain='B',
        ledger_id=ledger_id,
        symbol=_SYMBOL,
        discrepancy_type='quantity',
        expected_value=Money.shares_to_min_unit(expected),
        actual_value=Money.shares_to_min_unit(actual),
        diff=Money.shares_to_min_unit(actual - expected),
        status='pending',
    )
    db.add(d)
    db.flush()
    return d


def test_unknown_kind_is_rejected_and_writes_nothing(db, ledger):
    """旧后端会把没见过的 kind 当成「补录买入」；现在必须整笔拒绝。

    回归探针刻意带上 `quantity` / `avg_price`：那两个字段正是旧兜底分支用来写流水的入参，
    少了它们只能证明「没写库」，证明不了「兜底分支不再被走到」。
    """
    pos = _position(db, ledger.id, shares=60)
    txn_before = db.query(Transaction).count()

    with pytest.raises(ValueError, match='未知的裁决类型'):
        apply_decision(
            db,
            _FAMILY,
            {
                'kind': 'recompute_v2',  # 前端比后端新时的形态
                'symbol': _SYMBOL,
                'name': '华电国际',
                'asset_type': 'stock',
                'market': 'CN_A',
                'ledger_id': ledger.id,
                'quantity': 100,
                'avg_price': 10,
            },
        )

    assert db.query(Transaction).count() == txn_before, '未知 kind 不得写入流水'
    assert db.query(AdjustmentLog).count() == 0, '未知 kind 不得写审计'
    db.refresh(pos)
    assert pos.quantity == Money.shares_to_min_unit(60), '未知 kind 不得改持仓'


def test_unknown_kind_message_names_supported_actions_and_next_step(db):
    """提示必须同时给出「后端会什么」和「我该干什么」，否则用户只能猜。"""
    with pytest.raises(ValueError) as exc:
        apply_decision(db, _FAMILY, {'kind': 'rebalance', 'symbol': _SYMBOL})

    msg = str(exc.value)
    for kind in ('increment', 'set', 'anchor', 'recompute'):
        assert kind in msg, f'提示里缺少可用动作 {kind}'
    assert 'rebalance' in msg, '必须报出实际收到的 kind'
    assert '重启后端' in msg, '前后端版本错位时，下一步是重启后端而不是改数据'


def test_recompute_kind_still_dispatches(db, ledger):
    """白名单不得误伤现有动作：净额 0 的幽灵持仓按流水重算 → 标记清仓。"""
    pos = _position(db, ledger.id, shares=60)
    _txn(db, ledger.id, pos, 'buy', 60)
    _txn(db, ledger.id, pos, 'sell', 60, day=date(2026, 5, 2))
    disc = _disc(db, ledger.id, expected=0, actual=60)

    result = apply_decision(db, _FAMILY, {'kind': 'recompute', 'discrepancy_id': disc.id})

    assert result['action'] == 'recompute'
    db.refresh(pos)
    assert pos.quantity == 0
    assert pos.ownership_status == 'cleared'

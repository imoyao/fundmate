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
    """白名单不得误伤现有动作：派生额 > 0 时 recompute 照常执行并改写份额。

    旧版夹具是「净额 0 的幽灵持仓 → 标记清仓」，断言的恰是 #3135 **废除**的行为
    （份额真相是账单不是流水，派生 ≤ 0 不再等于清仓）。继续用那个夹具验证「能派发」，
    等于给已废除的契约背书。换成派生 40 份 / 账上 60 份：判据仍是「recompute 不被白名单
    误伤」，落点改为份额对齐到 40，且**不清仓**——清仓改由「改成账单份额 = 0」显式完成。
    """
    pos = _position(db, ledger.id, shares=60)
    _txn(db, ledger.id, pos, 'buy', 100)
    _txn(db, ledger.id, pos, 'sell', 60, day=date(2026, 5, 2))
    disc = _disc(db, ledger.id, expected=40, actual=60)

    result = apply_decision(db, _FAMILY, {'kind': 'recompute', 'discrepancy_id': disc.id})

    assert result['action'] == 'recompute'
    db.refresh(pos)
    assert pos.quantity == Money.shares_to_min_unit(40), '派生额 > 0 时应改写为派生份额'
    assert pos.ownership_status == 'active', '重算只对齐份额，不改持有状态'


def test_recompute_kind_refuses_to_clear_when_flows_net_zero(db, ledger):
    """派生额 ≤ 0 时 recompute 必须拒绝，且份额与审计一字不动（#3135）。

    这条是旧用例「净额 0 → 清仓」的**反向**：流水算到 0 多半是缺腿，据此清仓会把
    正确持仓清零。拒绝发生在写库之前，所以连审计都不该留。
    """
    pos = _position(db, ledger.id, shares=60)
    _txn(db, ledger.id, pos, 'buy', 60)
    _txn(db, ledger.id, pos, 'sell', 60, day=date(2026, 5, 2))
    disc = _disc(db, ledger.id, expected=0, actual=60)

    with pytest.raises(ValueError, match='不再按流水清仓'):
        apply_decision(db, _FAMILY, {'kind': 'recompute', 'discrepancy_id': disc.id})

    db.refresh(pos)
    assert pos.quantity == Money.shares_to_min_unit(60), '拒绝时不得改份额'
    assert pos.ownership_status == 'active', '拒绝时不得把持仓标成 cleared'
    assert db.query(AdjustmentLog).filter_by(action='position_recompute').count() == 0, '拒绝时不得写审计'

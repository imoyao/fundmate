# -*- coding: utf-8 -*-
"""「按流水重算份额」入口的行为测试（#3127）。

真库原型（只读实测，2026-11-15）：联创转债 #1012 份额 270 张、`active`，名下 16 条流水
净额 **0**（买 270 / 卖 270）——买入腿先被重建建成持仓、卖腿补码后回补，而回补按契约
只改归属不重算，于是「卖完了还挂着份额」。全库同形态 104 条（95 条由重建造出）。

本文件钉住补救入口的三件事：净额归零必须清仓（不是丢份额）、重复重算无副作用、
以及每次重算都留审计（改前 / 改后都要能回放）。
"""

from datetime import datetime

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.reconciliation.models import AdjustmentLog
from app.domains.transactions.models import Transaction
from app.services.position_recompute_entry import recompute_with_audit

_FAMILY = 1
_OTHER_FAMILY = 2
_BASE = datetime(2026, 3, 23, 9, 30, 0)


@pytest.fixture
def ledger(db):
    lg = Ledger(name='重算入口账户', ledger_type='bank', family_id=_FAMILY)
    db.add(lg)
    db.flush()
    return lg


def _mk_pos(db, ledger, *, shares, symbol='SZ128101', family_id=_FAMILY, status='active'):
    p = Position(
        family_id=family_id,
        ledger_id=ledger.id,
        symbol=symbol,
        name='联创转债',
        market='CN_A',
        currency='CNY',
        quantity=Money.shares_to_min_unit(shares),
        avg_price=Money.yuan_to_price_units(100.0),
        current_price=Money.yuan_to_price_units(100.0),
        ownership_status=status,
    )
    db.add(p)
    db.flush()
    return p


def _mk_txn(db, ledger, pos, *, txn_type, shares, symbol='SZ128101'):
    qty = Money.shares_to_min_unit(shares)
    price = Money.yuan_to_price_units(100.0)
    t = Transaction(
        family_id=_FAMILY,
        position_id=pos.id if pos else None,
        ledger_id=ledger.id,
        symbol=symbol,
        position_name='联创转债',
        asset_type='bond',
        txn_type=txn_type,
        quantity=qty,
        price=price,
        amount=Money.multiply_price_quantity(price, qty),
        realized_pnl=0,
        status='success',
        trade_date=_BASE,
        created_at=_BASE,
        updated_at=_BASE,
    )
    db.add(t)
    db.flush()
    return t


def test_recompute_clears_position_whose_flows_netted_out(db, ledger):
    """#3127 现场：份额 270、流水净额 0 ⇒ 重算必须清仓（保留行），并留审计。"""
    pos = _mk_pos(db, ledger, shares=270.0)
    _mk_txn(db, ledger, pos, txn_type='buy', shares=270.0)
    _mk_txn(db, ledger, pos, txn_type='sell', shares=270.0)

    data = recompute_with_audit(db, _FAMILY, pos.id, reason='回补后份额与流水不自洽')

    assert data['quantity_before'] == pytest.approx(270.0)
    assert data['quantity_after'] == pytest.approx(0.0)
    assert data['ownership_status_after'] == 'cleared'
    assert data['deleted'] is False  # 清仓保留行（#2343），不删行
    assert data['changed'] is True

    row = db.query(Position).filter_by(id=pos.id).one()
    assert row.quantity == 0
    assert row.ownership_status == 'cleared'

    log = db.query(AdjustmentLog).filter_by(action='position_recompute').one()
    assert data['log_id'] == log.id
    assert log.reason == '回补后份额与流水不自洽'


def test_recompute_is_idempotent(db, ledger):
    """重复点不该反复改：第二次 changed=False，份额与状态保持不变。"""
    pos = _mk_pos(db, ledger, shares=10.0)
    _mk_txn(db, ledger, pos, txn_type='buy', shares=4.0)

    first = recompute_with_audit(db, _FAMILY, pos.id)
    second = recompute_with_audit(db, _FAMILY, pos.id)

    assert first['changed'] is True
    assert first['quantity_after'] == pytest.approx(4.0)
    assert second['changed'] is False
    assert second['quantity_after'] == pytest.approx(4.0)


def test_recompute_deletes_empty_shell_and_says_so(db, ledger):
    """无流水且无锚点 ⇒ 空壳行被删。#1868 的判据：调用方要把 deleted 如实报出来。"""
    pos = _mk_pos(db, ledger, shares=7.0)

    data = recompute_with_audit(db, _FAMILY, pos.id)

    assert data['deleted'] is True
    assert data['quantity_after'] == pytest.approx(0.0)
    assert data['ownership_status_after'] == 'deleted'
    assert db.query(Position).filter_by(id=pos.id).first() is None
    assert db.query(AdjustmentLog).filter_by(action='position_recompute').count() == 1


def test_recompute_rejects_position_of_other_family(db, ledger):
    """跨家庭一律拒绝：这条入口直接改份额，绝不能靠「id 猜对了」就放行。"""
    pos = _mk_pos(db, ledger, shares=5.0, family_id=_OTHER_FAMILY)

    with pytest.raises(ValueError):
        recompute_with_audit(db, _FAMILY, pos.id)


def test_recompute_route_returns_before_after(client, db, ledger):
    """路由层：返回改前 / 改后，且 404 不泄露存在性。"""
    pos = _mk_pos(db, ledger, shares=3.0)
    _mk_txn(db, ledger, pos, txn_type='buy', shares=1.0)
    db.commit()

    resp = client.post(f'/api/positions/{pos.id}/recompute/', json={'reason': '手工核对'})

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['position_id'] == pos.id
    assert data['quantity_before'] == pytest.approx(3.0)
    assert data['quantity_after'] == pytest.approx(1.0)

    missing = client.post('/api/positions/999999/recompute/', json={})
    assert missing.status_code == 404

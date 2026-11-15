# -*- coding: utf-8 -*-
"""「以此为准」写锚点动作的回归网（#3125 A 方案）。

## 真库证据（为什么需要这个动作）

域 B 的 119 条数量差异 **100%** 来自无锚点持仓（`snapshot_quantity IS NULL`）：其中
101 条理论值为 0、4 条为负 —— 流水压根没覆盖建仓，不是份额记错。这类差异的修法不是
「补录这笔」（那等于让用户编造一笔不存在的交易去凑数），而是承认当前持仓为基准。

## 三条不容退让的判据

1. 写锚点**不改份额数值**（只把当前值固化成基准）；
2. 份额为 0 / 无成本价 / 无账本 **一律拒绝**，且错误信息指向真正可用的入口 ——
   拒绝得对但指错路，等于换个地方的死胡同；
3. 写完后重跑域 B，差异必须自己变成 `cleared`（否则用户会看到「点了没反应」）。
"""

from datetime import date

import pytest

from app.core.constants import AnchorKind
from app.core.money import Money
from app.core.time_utils import today_shanghai
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.reconciliation.models import AdjustmentLog, ReconciliationDiscrepancy
from app.domains.transactions.models import Transaction
from app.services.reconciliation_service import apply_decision, run_reconciliation

_DAY = date(2024, 6, 12)


@pytest.fixture
def ledger(db):
    lg = Ledger(name='银河证券', ledger_type='stock', family_id=1)
    db.add(lg)
    db.flush()
    return lg


def _position(db, ledger_id, shares=60, *, status='active', avg_price=10, anchor=None):
    p = Position(
        symbol='SH600027',
        name='华电国际',
        market='CN_A',
        asset_type='stock',
        ledger_id=ledger_id,
        family_id=1,
        quantity=Money.shares_to_min_unit(shares),
        avg_price=Money.yuan_to_price_units(avg_price) if avg_price else 0,
        current_price=Money.yuan_to_price_units(10),
        ownership_status=status,
        **(anchor or {}),
    )
    db.add(p)
    db.flush()
    return p


def _buy(db, ledger_id, shares=100, day=_DAY):
    t = Transaction(
        ledger_id=ledger_id,
        family_id=1,
        symbol='SH600027',
        txn_type='buy',
        confirm_date=day,
        quantity=Money.shares_to_min_unit(shares),
        price=Money.yuan_to_price_units(10),
        amount=Money.multiply_price_quantity(Money.yuan_to_price_units(10), Money.shares_to_min_unit(shares)),
        position_name='华电国际',
        asset_type='stock',
    )
    db.add(t)
    db.flush()
    return t


def _no_anchor_discrepancy(db, ledger_id):
    """跑一次域 B，取那条 no_anchor 差异（无锚点持仓 + 流水 100 vs 持仓 60）。"""
    run, _ = run_reconciliation(db, 1, 'B')
    return db.query(ReconciliationDiscrepancy).filter_by(last_run_id=run.id, discrepancy_type='no_anchor').one()


def test_anchor_decision_writes_manual_anchor_and_clears(db, ledger):
    """一次「以此为准」= 锚点三件套落库 + 差异自行 cleared + 审计留痕。"""
    pos = _position(db, ledger.id, shares=60)
    _buy(db, ledger.id, shares=100)
    db.commit()

    disc = _no_anchor_discrepancy(db, ledger.id)
    assert disc.status == 'pending'

    result = apply_decision(db, 1, {'kind': 'anchor', 'discrepancy_id': disc.id, 'reason': '券商快照为准'})
    db.commit()

    # 1) 锚点三件套：份额取持仓现值（60 份 → 最小单位），日期取业务日，来源 manual
    db.refresh(pos)
    assert pos.snapshot_quantity == Money.shares_to_min_unit(60)
    assert pos.snapshot_date == today_shanghai()
    assert pos.anchor_kind == AnchorKind.MANUAL.value
    # 2) 承诺：不改份额数值（锚点日之后没有流水，派生结果等于原值）
    assert pos.quantity == Money.shares_to_min_unit(60)
    # 3) 差异被重算轧平，用户在队列里看不到它了
    db.refresh(disc)
    assert disc.status == 'cleared'
    assert result['discrepancy']['status'] == 'cleared'
    # 4) 审计：action 单列 anchor，after 里留有锚点信息（可复盘「什么时候把哪只定了基准」）
    log = db.query(AdjustmentLog).filter_by(action='anchor').one()
    assert log.discrepancy_id == disc.id
    assert log.reason == '券商快照为准'
    assert str(Money.shares_to_min_unit(60)) in log.after_json


def test_anchor_decision_makes_next_run_silent(db, ledger):
    """写锚点之后重跑域 B，这条差异不再产生（不是被 ignore 掉，是不再成立）。"""
    _position(db, ledger.id, shares=60)
    _buy(db, ledger.id, shares=100)
    db.commit()

    disc = _no_anchor_discrepancy(db, ledger.id)
    apply_decision(db, 1, {'kind': 'anchor', 'discrepancy_id': disc.id})
    db.commit()

    run2, _ = run_reconciliation(db, 1, 'B')
    assert db.query(ReconciliationDiscrepancy).filter_by(last_run_id=run2.id, status='pending').count() == 0


def test_anchor_decision_rejects_zero_share_position(db, ledger):
    """份额为 0 的持仓写不了基准 —— 必须指回「按流水重建」，否则是另一条死胡同。"""
    pos = _position(db, ledger.id, shares=0, status='cleared')
    _buy(db, ledger.id, shares=100)
    db.commit()

    disc = db.query(ReconciliationDiscrepancy).filter_by(last_run_id=run_reconciliation(db, 1, 'B')[0].id).one()
    assert disc.discrepancy_type == 'quantity'  # 清仓行不进 no_anchor（见 service 判据注释）

    with pytest.raises(ValueError, match='按流水重建持仓'):
        apply_decision(db, 1, {'kind': 'anchor', 'discrepancy_id': disc.id})
    db.refresh(pos)
    assert pos.snapshot_quantity is None, '被拒时不得留下半条锚点'


def test_anchor_decision_rejects_position_without_cost(db, ledger):
    """无成本价的持仓写不了基准（快照要求单价 > 0），错误信息指向手填入口。"""
    _position(db, ledger.id, shares=60, avg_price=None)
    _buy(db, ledger.id, shares=100)
    db.commit()

    disc = _no_anchor_discrepancy(db, ledger.id)
    with pytest.raises(ValueError, match='成本单价'):
        apply_decision(db, 1, {'kind': 'anchor', 'discrepancy_id': disc.id})


def test_anchor_decision_requires_discrepancy(db, ledger):
    """没有差异就没有「以此为准」的对象 —— 拒绝，而不是猜一只持仓来写。"""
    with pytest.raises(ValueError, match='必须指定一条差异'):
        apply_decision(db, 1, {'kind': 'anchor'})


def test_anchor_decision_ignores_payload_symbol(db, ledger):
    """标的以**差异行**为准，不信 payload —— 前端传错也不能把别的标的定了基准。"""
    pos = _position(db, ledger.id, shares=60)
    _buy(db, ledger.id, shares=100)
    db.commit()

    disc = _no_anchor_discrepancy(db, ledger.id)
    apply_decision(
        db,
        1,
        {'kind': 'anchor', 'discrepancy_id': disc.id, 'symbol': 'SH999999', 'ledger_id': 999},
    )
    db.commit()

    db.refresh(pos)
    assert pos.snapshot_quantity == Money.shares_to_min_unit(60)
    assert db.query(Position).filter_by(symbol='SH999999').count() == 0, '不得因 payload 的标的另写一只持仓'

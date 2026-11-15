# -*- coding: utf-8 -*-
"""对账工作台「按流水重算份额」动作的回归网（#3134）。

## 这张网守的是什么

`quantity` 差异 = 持仓份额 − 按流水算出的份额。补录（increment）走买卖汇点，**同时**写
流水与持仓，差额两端同步移动 ⇒ 恒等于补录前的值。真库 2026-11-15 实测：用户照着卡片
提示补了一笔卖出 3000，持仓 4000→1000 份、流水 3000→0，差额仍是 1000 份
（`discrepancies#378`）。所以这类差异必须有一个**只改持仓**的动作，本条链就是它。

四条不容退让的判据：

1. 净额为 0 的幽灵持仓（买卖腿齐平却还挂着份额）⇒ 重算后份额 0 + `cleared`，差异自行消失；
2. 有锚点的持仓 ⇒ 重算按「锚点 + 期后流水」覆写份额（不把快照前的流水算进来）；
3. 净额为**负**（卖出多于买入，缺买入腿）⇒ **拒绝**，且错误信息指向手填入口
   —— 把「流水缺一条腿」当成「已清仓」是 #3127 明确禁止的批量清零；
4. 标的以**差异行**为准，payload 里的 symbol / ledger_id 不参与定位；
5. 流水一条都没挂到持仓上（悬空流水）⇒ **拒绝**，不得按「无流水且无锚点 ⇒ 删行」把一条
   有份额的持仓物理删除 —— 对账按 `(ledger_id, symbol)` 取流水、重算按 `position_id` 取，
   两套口径在那一刻分叉，而删行是静默且不可撤销的。

外加一条：审计必须回指差异（`action='position_recompute'` + `discrepancy_id`），
否则三周后没人说得清这次份额是被谁、因为哪条差异改的。
"""

from datetime import date

import pytest

from app.core.constants import AnchorKind, OwnershipStatus
from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.reconciliation.models import AdjustmentLog, ReconciliationDiscrepancy
from app.domains.transactions.models import Transaction
from app.services.reconciliation_service import apply_decision, run_reconciliation

_DAY = date(2024, 6, 12)
_SYMBOL = 'SH600027'


@pytest.fixture
def ledger(db):
    lg = Ledger(name='银河证券', ledger_type='stock', family_id=1)
    db.add(lg)
    db.flush()
    return lg


def _position(db, ledger_id, shares=60, *, status='active', anchor=None):
    p = Position(
        symbol=_SYMBOL,
        name='华电国际',
        market='CN_A',
        asset_type='stock',
        ledger_id=ledger_id,
        family_id=1,
        quantity=Money.shares_to_min_unit(shares),
        avg_price=Money.yuan_to_price_units(10),
        current_price=Money.yuan_to_price_units(10),
        ownership_status=status,
        **(anchor or {}),
    )
    db.add(p)
    db.flush()
    return p


def _txn(db, position, txn_type, shares, day=_DAY):
    """建一笔**已挂到持仓上**的流水：`compute_anchored_state` 按 `position_id` 取流水。"""
    t = Transaction(
        ledger_id=position.ledger_id,
        family_id=1,
        symbol=_SYMBOL,
        position_id=position.id,
        txn_type=txn_type,
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


def _quantity_discrepancy(db):
    run, _ = run_reconciliation(db, 1, 'B')
    return db.query(ReconciliationDiscrepancy).filter_by(last_run_id=run.id, discrepancy_type='quantity').one()


def test_recompute_clears_ghost_position_and_discrepancy(db, ledger):
    """净额 0 却还挂着 60 份 ⇒ 重算成清仓，差异自己消失（不是被 ignore 掉）。"""
    pos = _position(db, ledger.id, shares=60)
    _txn(db, pos, 'buy', 60)
    _txn(db, pos, 'sell', 60)
    db.commit()

    disc = _quantity_discrepancy(db)
    assert disc.status == 'pending'

    result = apply_decision(db, 1, {'kind': 'recompute', 'discrepancy_id': disc.id, 'reason': '按流水对齐'})
    db.commit()

    # 1) 份额归零 + cleared（#2343 起不删行，锚点/历史位保留）
    db.refresh(pos)
    assert pos.quantity == 0
    assert pos.ownership_status == OwnershipStatus.CLEARED.value
    # 2) 差异被重算轧平，队列里看不到它了
    db.refresh(disc)
    assert disc.status == 'cleared'
    assert result['discrepancy']['status'] == 'cleared'
    # 3) 重算是**只改持仓**：流水条数一条没变（补录才会新增流水）
    assert db.query(Transaction).filter_by(ledger_id=ledger.id, symbol=_SYMBOL).count() == 2
    # 4) 审计能回指这条差异
    log = db.query(AdjustmentLog).filter_by(action='position_recompute').one()
    assert log.discrepancy_id == disc.id
    assert log.reason == '按流水对齐'
    assert result['recompute']['quantity_before'] == 60
    assert result['recompute']['quantity_after'] == 0


def test_recompute_follows_anchor_plus_post_anchor_flows(db, ledger):
    """有锚点：只把锚点日之后的流水算进派生额，快照前流水不参与。"""
    pos = _position(
        db,
        ledger.id,
        shares=60,
        anchor={
            'snapshot_quantity': Money.shares_to_min_unit(60),
            'snapshot_date': _DAY,
            'anchor_kind': AnchorKind.MANUAL.value,
        },
    )
    _txn(db, pos, 'buy', 100, day=date(2024, 6, 13))
    db.commit()

    disc = _quantity_discrepancy(db)
    assert disc.discrepancy_type == 'quantity'

    apply_decision(db, 1, {'kind': 'recompute', 'discrepancy_id': disc.id})
    db.commit()

    db.refresh(pos)
    assert pos.quantity == Money.shares_to_min_unit(160), '锚点 60 + 期后买入 100'
    assert pos.snapshot_quantity == Money.shares_to_min_unit(60), '重算不得动锚点'
    db.refresh(disc)
    assert disc.status == 'cleared'


def test_recompute_rejects_oversell(db, ledger):
    """净额为负 ⇒ 拒绝重算，持仓与审计都不得被改。

    真库里这类是「买入腿没挂回来」（#3127 明确不敢批量清仓），照着流水重算等于
    把一只真有份额的持仓清零，且不会有任何提示。
    """
    pos = _position(db, ledger.id, shares=60)
    _txn(db, pos, 'buy', 40)
    _txn(db, pos, 'sell', 100)
    db.commit()

    disc = _quantity_discrepancy(db)
    assert disc.expected_value < 0

    with pytest.raises(ValueError, match='改成账单份额'):
        apply_decision(db, 1, {'kind': 'recompute', 'discrepancy_id': disc.id})
    db.commit()

    db.refresh(pos)
    assert pos.quantity == Money.shares_to_min_unit(60)
    assert pos.ownership_status == OwnershipStatus.ACTIVE.value
    assert db.query(AdjustmentLog).filter_by(action='position_recompute').count() == 0


def test_recompute_requires_existing_position(db, ledger):
    """差异指向的持仓已不存在 ⇒ 拒绝并指回重建入口，不猜一只持仓来改。"""
    disc = ReconciliationDiscrepancy(
        family_id=1,
        ledger_id=ledger.id,
        domain='B',
        symbol='SZ159981',
        discrepancy_type='quantity',
        expected_value=0,
        actual_value=Money.shares_to_min_unit(1000),
        diff=Money.shares_to_min_unit(1000),
        status='pending',
    )
    db.add(disc)
    db.commit()

    with pytest.raises(ValueError, match='按流水重建持仓'):
        apply_decision(db, 1, {'kind': 'recompute', 'discrepancy_id': disc.id})


def test_recompute_refuses_when_flows_are_unlinked(db, ledger):
    """流水一条都没挂到持仓上 ⇒ 拒绝，**不得**把这条有份额的持仓当空壳行删掉。

    对账按 `(ledger_id, symbol)` 取流水、重算按 `transactions.position_id` 取，两者在悬空
    流水下会分叉。若照重算的判据走（无流水且无锚点 ⇒ 删行），用户点「按流水重算份额」
    的结果是一条有 60 份的持仓被物理删除，而且报的是成功。
    """
    pos = _position(db, ledger.id, shares=60)
    for txn_type in ('buy', 'sell'):
        db.add(
            Transaction(
                ledger_id=ledger.id,
                family_id=1,
                symbol=_SYMBOL,
                position_id=None,
                txn_type=txn_type,
                confirm_date=_DAY,
                quantity=Money.shares_to_min_unit(60),
                price=Money.yuan_to_price_units(10),
                amount=Money.multiply_price_quantity(Money.yuan_to_price_units(10), Money.shares_to_min_unit(60)),
                position_name='华电国际',
                asset_type='stock',
            )
        )
    db.commit()

    disc = _quantity_discrepancy(db)
    assert disc.expected_value == 0, '两笔流水齐平 ⇒ 理论份额 0，而账上还有 60 份'
    with pytest.raises(ValueError, match='悬空流水'):
        apply_decision(db, 1, {'kind': 'recompute', 'discrepancy_id': disc.id})
    db.commit()

    assert db.query(Position).filter_by(id=pos.id).count() == 1, '持仓不得被删'
    db.refresh(pos)
    assert pos.quantity == Money.shares_to_min_unit(60)
    assert db.query(AdjustmentLog).filter_by(action='position_recompute').count() == 0


def test_recompute_requires_discrepancy(db, ledger):
    """没有差异就没有「按流水重算」的对象 —— 拒绝，而不是猜一只持仓来改。"""
    pos = _position(db, ledger.id, shares=60)
    _txn(db, pos, 'buy', 60)
    db.commit()

    with pytest.raises(ValueError, match='必须指定一条差异'):
        apply_decision(db, 1, {'kind': 'recompute'})


def test_recompute_uses_discrepancy_symbol_not_payload(db, ledger):
    """标的以差异行为准：payload 传别的标的也不能改到它。"""
    pos = _position(db, ledger.id, shares=60)
    _txn(db, pos, 'buy', 60)
    _txn(db, pos, 'sell', 60)
    other = Position(
        symbol='SZ000001',
        name='平安银行',
        market='CN_A',
        asset_type='stock',
        ledger_id=ledger.id,
        family_id=1,
        quantity=Money.shares_to_min_unit(500),
        avg_price=Money.yuan_to_price_units(10),
        current_price=Money.yuan_to_price_units(10),
        ownership_status='active',
    )
    db.add(other)
    db.commit()

    disc = _quantity_discrepancy(db)
    apply_decision(
        db,
        1,
        {'kind': 'recompute', 'discrepancy_id': disc.id, 'symbol': 'SZ000001', 'ledger_id': ledger.id},
    )
    db.commit()

    db.refresh(pos)
    db.refresh(other)
    assert pos.quantity == 0, '差异指向的持仓被重算'
    assert other.quantity == Money.shares_to_min_unit(500), 'payload 里的标的不得被改'

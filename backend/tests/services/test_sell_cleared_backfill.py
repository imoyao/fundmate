# -*- coding: utf-8 -*-
"""已清仓持仓的「历史卖出回填」不得被当前份额挡住（对账补录的死锁回归网）。

## 背景（SH600027 实测，2026-11-12）

用户在对账中心看到：按流水算 1,300 份 / 账上记的 0 份，差异类型 `orphan`
（界面标签「有持仓、缺流水」）。系统提示「补一笔流水」，他填了一笔
2026-05-14 卖出 1,300 股，提交被拒：

    持仓数量不足：当前持有 0.0，拟操作 1300

两处判断用了**两套持仓口径**：

- `run_reconciliation` 只把 `ownership_status='active'` 的持仓放进 map，
  已清仓行等于「没有持仓」⇒ 流水净额 > 0 ⇒ 报 orphan，建议补流水；
- `prepare_sell` 唯一的豁免是 `is_covered_by_anchor`，而它对非 active 持仓
  **恒返 False**，清仓行又通常没有锚点 ⇒ 必然落到「当前持有 0 < 拟操作 N」。

结果：**系统自己建议的修复路径永远走不通**。修复见 `is_backfill_of_past`：
「已清仓且流水日 <= cleared_at」与「锚点覆盖」并列，同属「只落流水、不驱动份额」。

本文件锁住：
1. 判定矩阵（清仓日边界 / 无 cleared_at / active 无锚点 / 日期不可解析）；
2. 补录历史卖出**成功落流水且份额不变**（0 是清仓后的事实，再减会变负）；
3. 清仓日**之后**的卖出仍被拦（真正的超卖不被放过）；
4. active 持仓超卖仍被拦（不回归）；
5. `apply_decision` 端到端（真实用户场景，payload 不带 `position_id`）；
6. 补完后 orphan 差异消失（两套口径重新一致）。
"""

from datetime import date, datetime

import pytest

from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.positions.state import is_backfill_of_past
from app.domains.reconciliation.models import ReconciliationDiscrepancy
from app.domains.transactions.models import Transaction
from app.services.position_service import PositionService
from app.services.reconciliation_service import DOMAIN_B, apply_decision, run_reconciliation

SYMBOL = 'SH600027'
CLEARED_AT = datetime(2026, 9, 28)
BACKFILL_DAY = date(2026, 5, 14)


@pytest.fixture
def ledger(db):
    lg = Ledger(name='同花顺（银河证券）', ledger_type='stock', family_id=1)
    db.add(lg)
    db.flush()
    return lg


def _position(db, ledger_id, *, quantity=0, status='cleared', cleared_at=CLEARED_AT, **overrides):
    pos = Position(
        symbol=SYMBOL,
        name='华电国际',
        market='CN_A',
        asset_type='stock',
        ledger_id=ledger_id,
        family_id=1,
        quantity=quantity,
        avg_price=46857,
        current_price=50000,
        ownership_status=status,
        cleared_at=cleared_at,
    )
    for key, value in overrides.items():
        setattr(pos, key, value)
    db.add(pos)
    db.flush()
    return pos


def _sell(db, ledger_id, pos, when, qty=1300, price=5.49, fee=4.64):
    return PositionService.process_sell_or_withdraw(
        db,
        {
            'position_id': pos.id,
            'symbol': SYMBOL,
            'ledger_id': ledger_id,
            'op_type': 'sell',
            'quantity': qty,
            'avg_price': price,
            'fee': fee,
            'trade_date': when,
            'confirm_date': when,
            'family_id': 1,
        },
    )


# ── 1. 判定矩阵 ──────────────────────────────────────────────


def test_cleared_backfill_matrix():
    """清仓日边界：`<=` 豁免，`>` 不豁免；缺 cleared_at / 无法解析日期一律不豁免。"""
    cleared = Position(symbol=SYMBOL, quantity=0, ownership_status='cleared', cleared_at=CLEARED_AT)
    assert is_backfill_of_past(cleared, date(2026, 5, 14)) is True
    assert is_backfill_of_past(cleared, date(2026, 9, 28)) is True  # 同日（清仓当天）
    assert is_backfill_of_past(cleared, date(2026, 10, 20)) is False
    assert is_backfill_of_past(cleared, '2026-05-14') is True  # ISO 字符串直传
    assert is_backfill_of_past(cleared, None) is False
    assert is_backfill_of_past(cleared, '2026-13-40') is False  # 解析失败 → 不豁免


def test_cleared_without_cleared_at_is_not_exempt():
    """历史清仓行可能没有 cleared_at，此时无法判定「清仓前/后」→ 保持旧行为拦下。"""
    pos = Position(symbol=SYMBOL, quantity=0, ownership_status='cleared', cleared_at=None)
    assert is_backfill_of_past(pos, date(2026, 5, 14)) is False


def test_active_position_still_uses_anchor_only():
    """active 持仓的口径不变：无锚点不豁免，有锚点且流水日 <= 快照日才豁免。"""
    no_anchor = Position(symbol=SYMBOL, quantity=1000, ownership_status='active')
    assert is_backfill_of_past(no_anchor, date(2026, 5, 14)) is False

    anchored = Position(
        symbol=SYMBOL,
        quantity=1000,
        ownership_status='active',
        snapshot_quantity=1000,
        snapshot_date=date(2026, 6, 1),
    )
    assert is_backfill_of_past(anchored, date(2026, 5, 14)) is True
    assert is_backfill_of_past(anchored, date(2026, 7, 1)) is False


# ── 2. 补录历史卖出：落流水、份额不动 ───────────────────────


def test_backfill_sell_on_cleared_position_records_txn_without_touching_qty(db, ledger):
    pos = _position(db, ledger.id)
    _sell(db, ledger.id, pos, BACKFILL_DAY)

    assert pos.quantity == 0, '清仓后补历史卖出不得再扣份额（否则变负数）'
    assert pos.ownership_status == 'cleared'
    txn = db.query(Transaction).one()
    assert txn.txn_type == 'sell'
    assert txn.quantity == 13_000_000  # 1300 份 × 10000
    assert txn.fee == 464  # 4.64 元 → 分
    assert txn.confirm_date == BACKFILL_DAY


def test_sell_after_cleared_at_still_rejected(db, ledger):
    """清仓日之后的卖出才是真超卖，豁免不能把它一起放过。"""
    pos = _position(db, ledger.id)
    with pytest.raises(ValueError, match='持仓数量不足'):
        _sell(db, ledger.id, pos, date(2026, 10, 20))
    assert db.query(Transaction).count() == 0


def test_active_position_oversell_still_rejected(db, ledger):
    """无回归：active 持仓超卖仍按原口径拦下。"""
    pos = _position(db, ledger.id, quantity=10_000_000, status='active', cleared_at=None)
    with pytest.raises(ValueError, match='持仓数量不足'):
        _sell(db, ledger.id, pos, date(2026, 10, 20), qty=1300)
    assert pos.quantity == 10_000_000


# ── 3. 真实场景端到端 + 差异收敛 ────────────────────────────


def test_apply_decision_backfills_cleared_sell(db, ledger):
    """用户的实际操作：payload 只有 (symbol, ledger_id)，不带 position_id。"""
    pos = _position(db, ledger.id)
    result = apply_decision(
        db,
        1,
        {
            'kind': 'increment',
            'symbol': SYMBOL,
            'ledger_id': ledger.id,
            'op_type': 'sell',
            'quantity': 1300,
            'avg_price': 5.49,
            'fee': 4.64,
            'trade_date': '2026-05-14',
            'confirm_date': '2026-05-14',
            'reason': '补一笔漏掉的卖出',
        },
    )
    assert result['action'] == 'supplement'
    assert result['after']['position_id'] == pos.id
    assert pos.quantity == 0
    assert db.query(Transaction).one().quantity == 13_000_000


def test_backfill_makes_orphan_discrepancy_disappear(db, ledger):
    """补完这笔卖出后，流水净额归零 → 对账不再报 orphan（两套口径重新一致）。"""
    pos = _position(db, ledger.id)
    # 流水里只有买入 1300（卖出的那笔缺失）——正是用户看到的「按流水算 1300 / 账上 0」
    db.add(
        Transaction(
            position_id=pos.id,
            symbol=SYMBOL,
            ledger_id=ledger.id,
            family_id=1,
            txn_type='buy',
            quantity=13_000_000,
            price=45800,
            confirm_date=date(2026, 4, 3),
            status='success',
            asset_type='stock',
        )
    )
    db.flush()

    run_reconciliation(db, 1, DOMAIN_B)
    pending = (
        db.query(ReconciliationDiscrepancy)
        .filter_by(family_id=1, symbol=SYMBOL, discrepancy_type='orphan', status='pending')
        .all()
    )
    assert len(pending) == 1, '先确认这条 orphan 真的会被报出来（否则下面的用例没有意义）'

    apply_decision(
        db,
        1,
        {
            'kind': 'increment',
            'symbol': SYMBOL,
            'ledger_id': ledger.id,
            'op_type': 'sell',
            'quantity': 1300,
            'avg_price': 5.49,
            'confirm_date': '2026-05-14',
        },
    )
    run_reconciliation(db, 1, DOMAIN_B)

    db.expire_all()
    still_pending = (
        db.query(ReconciliationDiscrepancy)
        .filter_by(family_id=1, symbol=SYMBOL, discrepancy_type='orphan', status='pending')
        .all()
    )
    assert still_pending == [], '补完漏掉的卖出后，orphan 必须消失'

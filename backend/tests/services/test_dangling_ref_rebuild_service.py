# -*- coding: utf-8 -*-
"""悬空流水「按流水重建持仓」服务的单元测试。

复用仓库既有 ``db`` fixture（临时文件库 + autouse clean_db），直接把 Session 传给纯业务
函数，与视图 ``with user_session() as db:`` 的单事务同构，全程不依赖 Flask / 不碰真库。

真实事故原型（只读实测，2026-11-12）：``transactions#2834`` 是 2026-03-23 买入 3700 份
SH515250（金额 3855.40 元），``position_id=596`` 指向**已不存在**的持仓行——旧版「整笔卖出
清仓」走 ``db.delete(position)``，流水不级联。于是补录卖出报「找不到这笔持仓」。本文件钉住
「**以流水为真相源**重建那一行」的每条判据。
"""

import json
from datetime import datetime

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.reconciliation.models import AdjustmentLog
from app.domains.transactions.models import Transaction
from app.services import dangling_ref_rebuild_service as svc

_FAMILY = 1
_OTHER_FAMILY = 2
_DANGLING_PID = 990001  # 不存在的持仓 id（position_id 无外键，可安全写入）
_BASE = datetime(2026, 3, 23, 9, 30, 0)  # 固定 created_at / updated_at
_SYMBOL = 'SH515250'
_NAME = '智能汽车'


@pytest.fixture
def ledger(db):
    lg = Ledger(name='重建-测试账户', ledger_type='bank', family_id=_FAMILY)
    db.add(lg)
    db.flush()
    return lg


@pytest.fixture
def ledger2(db):
    lg = Ledger(name='重建-第二账户', ledger_type='bank', family_id=_FAMILY)
    db.add(lg)
    db.flush()
    return lg


def _mk_txn(
    db,
    ledger_id,
    *,
    position_id=_DANGLING_PID,
    family_id=_FAMILY,
    symbol=_SYMBOL,
    position_name=_NAME,
    asset_type='stock',
    txn_type='buy',
    shares=1.0,
    price_yuan=1.0,
    trade_date=None,
):
    """建一条流水。position_id 默认指向不存在的持仓（悬空）；symbol_norm 交给 mapper 事件。"""
    price = Money.yuan_to_price_units(price_yuan)
    qty = Money.shares_to_min_unit(shares)
    t = Transaction(
        family_id=family_id,
        position_id=position_id,
        ledger_id=ledger_id,
        symbol=symbol,
        position_name=position_name,
        asset_type=asset_type,
        txn_type=txn_type,
        quantity=qty,
        price=price,
        amount=Money.multiply_price_quantity(price, qty),
        realized_pnl=0,
        status='success',
        trade_date=trade_date,
        created_at=_BASE,
        updated_at=_BASE,
    )
    db.add(t)
    db.flush()
    return t


def _mk_pos(db, ledger_id, symbol, shares, *, family_id=_FAMILY):
    qty = Money.shares_to_min_unit(shares)
    p = Position(
        family_id=family_id,
        ledger_id=ledger_id,
        symbol=symbol,
        name=symbol,
        market='CN_A',
        currency='CNY',
        quantity=qty,
        avg_price=Money.yuan_to_price_units(1.0),
        current_price=Money.yuan_to_price_units(1.0),
    )
    db.add(p)
    db.flush()
    return p


def _assert_rejected(db, fn, match):
    """拒绝分支不得留下未决写入、不得新增持仓 / 审计日志。"""
    positions_before = db.query(Position).count()
    logs_before = db.query(AdjustmentLog).count()
    with pytest.raises(ValueError, match=match):
        fn()
    assert not db.new and not db.dirty and not db.deleted, '拒绝分支不得留下未决写入'
    assert db.query(Position).count() == positions_before, '拒绝分支不得建持仓'
    assert db.query(AdjustmentLog).count() == logs_before, '拒绝分支不得写审计日志'


# ── preview：口径正确 + 纯只读 ─────────────────────────────────────────────


def test_preview_derives_quantity_and_cost_from_txns(db, ledger):
    """买入 3700 份 @1.042 + 卖出 1000 份 → 净 2700 份，成本按买入加权。"""
    buy = _mk_txn(db, ledger.id, shares=3700, price_yuan=1.042)
    sell = _mk_txn(db, ledger.id, txn_type='sell', shares=1000, price_yuan=1.1)

    data = svc.preview_rebuild(db, _FAMILY, [buy.id, sell.id])

    assert data['rebuildable'] is True
    assert data['block_reason'] is None
    assert data['txn_count'] == 2
    assert data['symbol'] == _SYMBOL
    assert data['display_name'] == _NAME, '标题用名称，代码只作事实行'
    assert data['ledger_id'] == ledger.id
    assert data['ledger_name'] == '重建-测试账户'
    assert data['net_units'] == pytest.approx(2700.0)
    assert data['avg_price'] == pytest.approx(1.042)
    assert isinstance(data['warnings'], list) and data['warnings']


def test_preview_is_strictly_readonly(db, ledger):
    """预览不建持仓、不改流水、不写审计日志。"""
    t = _mk_txn(db, ledger.id, shares=100)

    svc.preview_rebuild(db, _FAMILY, [t.id])

    assert db.query(Position).count() == 0
    assert db.query(AdjustmentLog).count() == 0
    assert db.query(Transaction).filter_by(id=t.id).one().position_id == _DANGLING_PID


def test_preview_warns_when_no_buy_leg(db, ledger):
    """组内只有送股（无买入腿）→ 份额有、成本恒 0，必须如实告知（否则市值与收益静默偏小）。"""
    t = _mk_txn(db, ledger.id, txn_type='split', shares=100, price_yuan=0)

    data = svc.preview_rebuild(db, _FAMILY, [t.id])

    assert data['rebuildable'] is True
    assert data['net_units'] == pytest.approx(100.0)
    assert data['avg_price'] == 0
    assert any('成本' in w for w in data['warnings'])


def test_preview_warns_when_sibling_txns_not_selected(db, ledger):
    """同账本同标的还有没选进来的悬空流水 → 必须提示份额会偏小（最大真实风险）。"""
    chosen = _mk_txn(db, ledger.id, shares=100)
    _mk_txn(db, ledger.id, shares=200)  # 同标的另一条悬空流水，故意不选

    data = svc.preview_rebuild(db, _FAMILY, [chosen.id])

    assert data['rebuildable'] is True
    assert data['net_units'] == pytest.approx(100.0)
    assert any('没有选进来' in w for w in data['warnings'])


def test_preview_has_no_sibling_warning_when_all_selected(db, ledger):
    """把同标的悬空流水全选上就不该有该提示（否则是噪声，会让人忽略真提示）。"""
    a = _mk_txn(db, ledger.id, shares=100)
    b = _mk_txn(db, ledger.id, shares=200)

    data = svc.preview_rebuild(db, _FAMILY, [a.id, b.id])

    assert not any('没有选进来' in w for w in data['warnings'])


# ── rebuild：正常重建并挂回 ───────────────────────────────────────────────


def test_rebuild_creates_position_and_reattaches_txns(db, ledger):
    """重建后：持仓行新建、份额成本来自流水、流水全部挂到新行、审计两侧快照齐全。"""
    buy = _mk_txn(db, ledger.id, shares=3700, price_yuan=1.042)
    sell = _mk_txn(db, ledger.id, txn_type='sell', shares=1000, price_yuan=1.1)

    data = svc.rebuild_position(db, _FAMILY, [buy.id, sell.id], reason='补建缺失持仓', confirm=True)

    pos = db.query(Position).filter_by(id=data['position_id']).one()
    assert pos.symbol == _SYMBOL
    assert pos.name == _NAME
    assert pos.ledger_id == ledger.id
    assert pos.quantity == Money.shares_to_min_unit(2700)
    assert pos.avg_price == Money.yuan_to_price_units(1.042)
    for t in (buy, sell):
        assert db.query(Transaction).filter_by(id=t.id).one().position_id == pos.id

    log = db.query(AdjustmentLog).filter_by(id=data['log_id']).one()
    assert log.action == svc.ACTION_REBUILD
    assert log.family_id == _FAMILY
    assert log.reason == '补建缺失持仓'
    before = json.loads(log.before_json)
    after = json.loads(log.after_json)
    assert before['txn_position_ids'][str(buy.id)] == _DANGLING_PID
    assert after['position_id'] == pos.id
    assert sorted(after['txn_ids']) == sorted([buy.id, sell.id])


def test_rebuild_requires_strict_confirm(db, ledger):
    """``confirm`` 必须是布尔 ``True``：``1`` / ``'true'`` 一律拒绝且零写入。"""
    t = _mk_txn(db, ledger.id, shares=100)

    _assert_rejected(db, lambda: svc.rebuild_position(db, _FAMILY, [t.id], confirm=1), 'confirm 必须为 true')
    _assert_rejected(db, lambda: svc.rebuild_position(db, _FAMILY, [t.id], confirm='true'), 'confirm 必须为 true')


# ── 五条拒绝判据 ─────────────────────────────────────────────────────────


def test_rebuild_rejects_net_non_positive(db, ledger):
    """买卖已对冲（净额 0）→ 拒绝：建 0 份额空壳行只是换一种脏数据。"""
    buy = _mk_txn(db, ledger.id, shares=100, price_yuan=1.0)
    sell = _mk_txn(db, ledger.id, txn_type='sell', shares=100, price_yuan=1.0)

    data = svc.preview_rebuild(db, _FAMILY, [buy.id, sell.id])
    assert data['rebuildable'] is False and '净额' in data['block_reason']

    _assert_rejected(
        db, lambda: svc.rebuild_position(db, _FAMILY, [buy.id, sell.id], confirm=True), '净额'
    )


def test_rebuild_rejects_existing_position_row(db, ledger):
    """同账本已有同标的持仓行 → 拒绝，并指向「回补关联」（两条写路径不能重叠）。"""
    _mk_pos(db, ledger.id, _SYMBOL, 10)
    t = _mk_txn(db, ledger.id, shares=100)

    data = svc.preview_rebuild(db, _FAMILY, [t.id])
    assert data['rebuildable'] is False and '回补关联' in data['block_reason']

    _assert_rejected(
        db, lambda: svc.rebuild_position(db, _FAMILY, [t.id], confirm=True), '回补关联'
    )


def test_rebuild_rejects_cross_ledger_group(db, ledger, ledger2):
    """组内跨账本 → 拒绝：重建行只能落在一个账本里。"""
    t1 = _mk_txn(db, ledger.id, shares=100)
    t2 = _mk_txn(db, ledger2.id, shares=100)

    data = svc.preview_rebuild(db, _FAMILY, [t1.id, t2.id])
    assert data['rebuildable'] is False and '账本' in data['block_reason']

    _assert_rejected(
        db, lambda: svc.rebuild_position(db, _FAMILY, [t1.id, t2.id], confirm=True), '账本'
    )


def test_rebuild_rejects_missing_symbol(db, ledger):
    """缺标的代码 → 拒绝，并指向「补全信息」（重建先要知道建哪个持仓）。"""
    t = _mk_txn(db, ledger.id, symbol='', position_name=None, shares=100)

    data = svc.preview_rebuild(db, _FAMILY, [t.id])
    assert data['rebuildable'] is False and '补全信息' in data['block_reason']

    _assert_rejected(
        db, lambda: svc.rebuild_position(db, _FAMILY, [t.id], confirm=True), '补全信息'
    )


def test_rebuild_rejects_buy_without_price(db, ledger):
    """买入缺成交价 → 派生不出成本，拒绝（``Decimal(str(None))`` 会直接抛在派生里）。"""
    t = _mk_txn(db, ledger.id, shares=100)
    db.query(Transaction).filter_by(id=t.id).one().price = None
    db.flush()

    data = svc.preview_rebuild(db, _FAMILY, [t.id])
    assert data['rebuildable'] is False and '成交价' in data['block_reason']

    _assert_rejected(
        db, lambda: svc.rebuild_position(db, _FAMILY, [t.id], confirm=True), '成交价'
    )


def test_rebuild_rejects_non_dangling_or_other_family(db, ledger):
    """已挂回现存持仓 / 属于别的家庭 → 整体拒绝（不写任何东西）。"""
    pos = _mk_pos(db, ledger.id, _SYMBOL, 10)
    attached = _mk_txn(db, ledger.id, position_id=pos.id, shares=1)
    other = _mk_txn(db, ledger.id, family_id=_OTHER_FAMILY, shares=1)

    with pytest.raises(ValueError, match='并非悬空'):
        svc.preview_rebuild(db, _FAMILY, [attached.id])
    with pytest.raises(ValueError, match='并非悬空'):
        svc.preview_rebuild(db, _FAMILY, [other.id])


# ── undo：可撤销 / 幂等留痕 / 期间被改过则跳过 ─────────────────────────────


def test_undo_restores_dangling_state_and_deletes_position(db, ledger):
    """撤销后：流水回到悬空、新持仓删除、追加一条撤销日志。"""
    buy = _mk_txn(db, ledger.id, shares=100)
    data = svc.rebuild_position(db, _FAMILY, [buy.id], confirm=True)
    pid = data['position_id']

    result = svc.undo_rebuild(db, _FAMILY, data['log_id'])

    assert result['restored'] == 1 and result['skipped'] == 0
    assert db.query(Position).filter_by(id=pid).first() is None
    assert db.query(Transaction).filter_by(id=buy.id).one().position_id == _DANGLING_PID
    assert db.query(AdjustmentLog).filter_by(action=svc.ACTION_REBUILD_UNDO).count() == 1


def test_undo_skips_when_position_changed(db, ledger):
    """期间补录了卖出（份额变了）→ 跳过并给原因，绝不抹掉后来的业务事实。"""
    buy = _mk_txn(db, ledger.id, shares=100)
    data = svc.rebuild_position(db, _FAMILY, [buy.id], confirm=True)
    pos = db.query(Position).filter_by(id=data['position_id']).one()
    pos.quantity = Money.shares_to_min_unit(50)
    db.flush()

    result = svc.undo_rebuild(db, _FAMILY, data['log_id'])

    assert result['skipped'] == 1 and result['restored'] == 0
    assert '已被改动' in result['skip_reason']
    assert db.query(Position).filter_by(id=data['position_id']).first() is not None
    assert db.query(Transaction).filter_by(id=buy.id).one().position_id == data['position_id']


def test_undo_skips_when_position_gone(db, ledger):
    """持仓已被删除 → 跳过（幂等）：重复撤销不抛错、数据不再变化，但仍留痕。"""
    buy = _mk_txn(db, ledger.id, shares=100)
    data = svc.rebuild_position(db, _FAMILY, [buy.id], confirm=True)
    db.delete(db.query(Position).filter_by(id=data['position_id']).one())
    db.flush()

    result = svc.undo_rebuild(db, _FAMILY, data['log_id'])

    assert result['skipped'] == 1 and '已不存在' in result['skip_reason']
    assert db.query(AdjustmentLog).filter_by(action=svc.ACTION_REBUILD_UNDO).count() == 1


def test_undo_rejects_foreign_or_wrong_log(db, ledger):
    """只能撤销本家庭的 ``dangling_ref_rebuild`` 日志；别的 action / 别的家庭一律拒绝。"""
    buy = _mk_txn(db, ledger.id, shares=100)
    data = svc.rebuild_position(db, _FAMILY, [buy.id], confirm=True)

    with pytest.raises(ValueError, match='撤销记录不存在'):
        svc.undo_rebuild(db, _OTHER_FAMILY, data['log_id'])

    other_log = AdjustmentLog(family_id=_FAMILY, action='dangling_ref_enrich', before_json='[]', after_json='[]')
    db.add(other_log)
    db.flush()
    with pytest.raises(ValueError, match='撤销记录不存在'):
        svc.undo_rebuild(db, _FAMILY, other_log.id)

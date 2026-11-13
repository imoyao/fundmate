# -*- coding: utf-8 -*-
"""「流水挂到了别的标的的持仓上」的检出与改挂（域 F 新阶段）单元测试。

真实原型（真库只读实测，2026-11-13）：``transactions#1954`` 是买入 ``SZ127041``，
``position_id=488`` 却指向 ``SZ128033`` 的现存持仓；``#2355``（``SH601058`` →
``SH600567``）、``#2785``（``SZ159981`` → ``SZ000725``）同型。这三条既不被
``_dangling_condition`` 认出（持仓行存在），又让 ``run_reconciliation`` 每轮都重新
产出它们自己标的的 orphan 差异 —— 于是「永远 pending、又没有任何入口能修」。

复用仓库既有 ``db`` fixture（临时文件库），直接把 Session 传给纯业务函数，
与视图 ``with user_session() as db:`` 的单事务同构，不依赖 Flask / 不碰真库。
"""

import json
from datetime import datetime

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.positions.state import derive_state_from_txns
from app.domains.reconciliation.models import AdjustmentLog
from app.domains.transactions.models import Transaction
from app.services import dangling_ref_mislink_service as svc

_FAMILY = 1
_OTHER_FAMILY = 2
_BASE = datetime(2026, 3, 23, 9, 30, 0)

#: 流水自己的标的（本该挂到的）
_SYMBOL = 'SZ127041'
_NAME = '弘亚转债'
#: 它被错挂到的持仓标的
_WRONG_SYMBOL = 'SZ128033'


@pytest.fixture
def ledger(db):
    lg = Ledger(name='错挂-测试账户', ledger_type='bank', family_id=_FAMILY)
    db.add(lg)
    db.flush()
    return lg


@pytest.fixture
def ledger2(db):
    lg = Ledger(name='错挂-第二账户', ledger_type='bank', family_id=_FAMILY)
    db.add(lg)
    db.flush()
    return lg


def _mk_pos(db, ledger_id, symbol, shares, *, family_id=_FAMILY, asset_type='bond', name=None):
    p = Position(
        family_id=family_id,
        ledger_id=ledger_id,
        symbol=symbol,
        name=name or symbol,
        asset_type=asset_type,
        market='CN_A',
        currency='CNY',
        quantity=Money.shares_to_min_unit(shares),
        avg_price=Money.yuan_to_price_units(1.0),
        current_price=Money.yuan_to_price_units(1.0),
    )
    db.add(p)
    db.flush()
    return p


def _mk_txn(
    db,
    ledger_id,
    position_id,
    *,
    symbol=_SYMBOL,
    asset_type='bond',
    txn_type='buy',
    shares=10.0,
    price_yuan=1.0,
    family_id=_FAMILY,
    position_name=_NAME,
):
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
        trade_date=None,
        created_at=_BASE,
        updated_at=_BASE,
    )
    db.add(t)
    db.flush()
    return t


def _mk_mislink(db, ledger_id, *, wrong_symbol=_WRONG_SYMBOL, **kw):
    """流水挂在「别的标的」的现存持仓上（本文件的主角）。"""
    wrong = _mk_pos(db, ledger_id, wrong_symbol, 30)
    txn = _mk_txn(db, ledger_id, wrong.id, **kw)
    return txn, wrong


def _assert_rejected(db, fn, match):
    """拒绝分支不得留下未决写入、不得新增持仓 / 审计日志。"""
    positions_before = db.query(Position).count()
    logs_before = db.query(AdjustmentLog).count()
    with pytest.raises(ValueError, match=match):
        fn()
    assert not db.new and not db.dirty and not db.deleted, '拒绝分支不得留下未决写入'
    assert db.query(Position).count() == positions_before, '拒绝分支不得建持仓'
    assert db.query(AdjustmentLog).count() == logs_before, '拒绝分支不得写审计日志'


# ── 检出 ────────────────────────────────────────────────────────────────


def test_scan_detects_txn_attached_to_other_symbol(db, ledger):
    """流水 A 挂在标的 B 的现存持仓上 → 单独成组，并说清「现在挂在哪、要怎么改」。"""
    txn, wrong = _mk_mislink(db, ledger.id)

    data = svc.scan_mislinked_refs(db, _FAMILY)

    assert data['total'] == 1 and data['group_count'] == 1
    assert data['fixable_count'] == 1
    group = data['groups'][0]
    assert group['key'] == f'mislink|{ledger.id}|{_SYMBOL}', 'key 必须与悬空组区分开'
    assert group['symbol'] == _SYMBOL
    assert group['mislinked'] is True
    assert [t['id'] for t in group['transactions']] == [txn.id]
    assert [(p['id'], p['symbol']) for p in group['wrong_positions']] == [(wrong.id, _WRONG_SYMBOL)]
    assert group['live_position'] is None, '没有任何同标的持仓可挂 → 只能按流水重建'
    assert group['fix_mode'] == svc.MODE_REBUILD
    assert group['fixable'] is True and group['block_reason'] is None
    assert 'mislinked' in group['flags'] and 'no_target' in group['flags']


def test_scan_ignores_same_code_different_venue(db, ledger):
    """同一代码但交易场所标注不同（``SZ004369`` 流水 vs ``004369`` 场外持仓）**不算**错挂。

    真库实测 24 条 symbol_norm 不等的挂接里有 21 条是这种「代码相同、asset_type 不同」，
    拿含场所的身份键当判据会把这 21 条一起推给用户 —— 那是场所标注问题，按它改挂会改坏持仓。
    """
    fund = _mk_pos(db, ledger.id, '004369', 100, asset_type='fund')
    _mk_txn(db, ledger.id, fund.id, symbol='SZ004369', asset_type='stock', position_name='场外基金')

    data = svc.scan_mislinked_refs(db, _FAMILY)

    assert data['total'] == 0, '同一代码不同场所不是「挂错标的」'


def test_scan_ignores_correct_attachment(db, ledger):
    """正常挂接（同标的）与别的家庭一律不检出。"""
    pos = _mk_pos(db, ledger.id, _SYMBOL, 30)
    _mk_txn(db, ledger.id, pos.id)
    other = _mk_pos(db, ledger.id, _WRONG_SYMBOL, 30, family_id=_OTHER_FAMILY)
    _mk_txn(db, ledger.id, other.id, family_id=_OTHER_FAMILY)

    data = svc.scan_mislinked_refs(db, _FAMILY)

    assert data['total'] == 0


# ── 预览 ────────────────────────────────────────────────────────────────


def test_preview_is_strictly_readonly(db, ledger):
    """预览不建持仓、不改流水、不写审计日志。"""
    txn, wrong = _mk_mislink(db, ledger.id)

    data = svc.preview_mislink_fix(db, _FAMILY, [txn.id])

    assert data['fixable'] is True
    assert data['mode'] == svc.MODE_REBUILD
    assert data['target_position'] is None
    assert data['net_units'] == pytest.approx(10.0)
    assert data['avg_price'] == pytest.approx(1.0)
    assert data['wrong_position_ids'] == [wrong.id]
    assert data['warnings'], '必须如实告知「错误持仓份额不会自动重算」'
    assert any('重算' in w for w in data['warnings'])
    assert db.query(Position).count() == 1
    assert db.query(AdjustmentLog).count() == 0
    assert db.query(Transaction).filter_by(id=txn.id).one().position_id == wrong.id


# ── 改挂：重建模式（真库那三条的形态）──────────────────────────────────


def test_fix_rebuild_mode_creates_correct_position_and_remounts(db, ledger):
    """没有同标的持仓行 → 按流水新建正确标的的持仓，流水改指过去，错误持仓不再含这笔。"""
    txn, wrong = _mk_mislink(db, ledger.id)
    wrong_qty_before = wrong.quantity

    data = svc.fix_mislink(db, _FAMILY, [txn.id], reason='改挂到正确标的', confirm=True)

    pos = db.query(Position).filter_by(id=data['position_id']).one()
    assert pos.symbol == _SYMBOL
    assert pos.ledger_id == ledger.id
    assert data['mode'] == svc.MODE_REBUILD
    assert data['created_position_id'] == pos.id
    assert db.query(Transaction).filter_by(id=txn.id).one().position_id == pos.id

    # 错误持仓：流水集合里不再有这笔，派生份额也不含它；但份额列一字未动（不静默改账）
    wrong_txns = db.query(Transaction).filter(Transaction.position_id == wrong.id).all()
    assert [t.id for t in wrong_txns] == []
    assert derive_state_from_txns(wrong_txns, 0, 0)[0] == 0
    assert db.query(Position).filter_by(id=wrong.id).one().quantity == wrong_qty_before

    log = db.query(AdjustmentLog).filter_by(id=data['log_id']).one()
    assert log.action == svc.ACTION_MISLINK
    assert log.family_id == _FAMILY
    assert log.reason == '改挂到正确标的'
    before = json.loads(log.before_json)
    after = json.loads(log.after_json)
    assert before == [{'id': txn.id, 'position_id': wrong.id}]
    assert after['position_id'] == pos.id and after['txn_ids'] == [txn.id]


def test_fix_remount_mode_reuses_existing_position(db, ledger):
    """同账本已有同标的持仓行 → 只改指针，不新建持仓、份额不动。"""
    txn, wrong = _mk_mislink(db, ledger.id)
    target = _mk_pos(db, ledger.id, _SYMBOL, 10)
    positions_before = db.query(Position).count()

    data = svc.fix_mislink(db, _FAMILY, [txn.id], confirm=True)

    assert data['mode'] == svc.MODE_REMOUNT
    assert data['position_id'] == target.id
    assert data['created_position_id'] is None
    assert db.query(Position).count() == positions_before, '回补模式不得新建持仓'
    assert db.query(Transaction).filter_by(id=txn.id).one().position_id == target.id
    assert db.query(Position).filter_by(id=target.id).one().quantity == target.quantity


def test_fix_requires_strict_confirm(db, ledger):
    """``confirm`` 必须是布尔 ``True``：``1`` / ``'true'`` 一律拒绝且零写入。"""
    txn, _ = _mk_mislink(db, ledger.id)

    _assert_rejected(db, lambda: svc.fix_mislink(db, _FAMILY, [txn.id], confirm=1), 'confirm 必须为 true')
    _assert_rejected(db, lambda: svc.fix_mislink(db, _FAMILY, [txn.id], confirm='true'), 'confirm 必须为 true')


# ── 拒绝判据 ────────────────────────────────────────────────────────────


def test_fix_rejects_correct_attachment_or_other_family(db, ledger):
    """已正常挂接 / 属于别的家庭 → 整体拒绝（不写任何东西），并说清为什么。"""
    pos = _mk_pos(db, ledger.id, _SYMBOL, 30)
    attached = _mk_txn(db, ledger.id, pos.id)
    other = _mk_txn(db, ledger.id, pos.id, family_id=_OTHER_FAMILY)

    with pytest.raises(ValueError, match='并非「挂错标的」'):
        svc.preview_mislink_fix(db, _FAMILY, [attached.id])
    with pytest.raises(ValueError, match='并非「挂错标的」'):
        svc.preview_mislink_fix(db, _FAMILY, [other.id])


def test_fix_rejects_cross_ledger_group(db, ledger, ledger2):
    """组内跨账本 → 拒绝：改挂只能落到一个账本的持仓上。"""
    t1, _ = _mk_mislink(db, ledger.id)
    t2, _ = _mk_mislink(db, ledger2.id, wrong_symbol='SH600567')

    data = svc.preview_mislink_fix(db, _FAMILY, [t1.id, t2.id])
    assert data['fixable'] is False and '账本' in data['block_reason']

    _assert_rejected(db, lambda: svc.fix_mislink(db, _FAMILY, [t1.id, t2.id], confirm=True), '账本')


def test_fix_rejects_venue_conflict_target(db, ledger):
    """同账本只有「代码相同、场所不同」的持仓 → 拒绝并指向人工核对，绝不猜场所。"""
    txn, _ = _mk_mislink(db, ledger.id)
    _mk_pos(db, ledger.id, '127041', 100, asset_type='fund')  # 场外裸码 → OTC，与流水 EXCHANGE 不同

    data = svc.preview_mislink_fix(db, _FAMILY, [txn.id])

    assert data['fixable'] is False
    assert '交易场所' in data['block_reason']
    _assert_rejected(db, lambda: svc.fix_mislink(db, _FAMILY, [txn.id], confirm=True), '交易场所')


def test_fix_rejects_net_non_positive(db, ledger):
    """净额 ≤ 0 且没有可挂回的持仓 → 拒绝：建 0 份额空壳行只是换一种脏数据。"""
    wrong = _mk_pos(db, ledger.id, _WRONG_SYMBOL, 30)
    buy = _mk_txn(db, ledger.id, wrong.id, shares=10)
    sell = _mk_txn(db, ledger.id, wrong.id, txn_type='sell', shares=10)

    data = svc.preview_mislink_fix(db, _FAMILY, [buy.id, sell.id])
    assert data['fixable'] is False and '净额' in data['block_reason']

    _assert_rejected(db, lambda: svc.fix_mislink(db, _FAMILY, [buy.id, sell.id], confirm=True), '净额')


# ── 撤销 ────────────────────────────────────────────────────────────────


def test_undo_rebuild_mode_restores_pointer_and_deletes_position(db, ledger):
    """撤销重建模式的改挂：流水放回原持仓、新建的持仓删掉、追加留痕日志。"""
    txn, wrong = _mk_mislink(db, ledger.id)
    data = svc.fix_mislink(db, _FAMILY, [txn.id], confirm=True)
    created = data['position_id']

    result = svc.undo_mislink(db, _FAMILY, data['log_id'])

    assert result['restored'] == 1 and result['skipped'] == 0
    assert db.query(Position).filter_by(id=created).first() is None
    assert db.query(Transaction).filter_by(id=txn.id).one().position_id == wrong.id
    assert db.query(AdjustmentLog).filter_by(action=svc.ACTION_MISLINK_UNDO).count() == 1


def test_undo_remount_mode_keeps_target_position(db, ledger):
    """撤销回补模式的改挂：流水放回原持仓，目标持仓本就不是本次建的，不能删。"""
    txn, wrong = _mk_mislink(db, ledger.id)
    target = _mk_pos(db, ledger.id, _SYMBOL, 10)
    data = svc.fix_mislink(db, _FAMILY, [txn.id], confirm=True)

    result = svc.undo_mislink(db, _FAMILY, data['log_id'])

    assert result['restored'] == 1
    assert db.query(Position).filter_by(id=target.id).first() is not None
    assert db.query(Transaction).filter_by(id=txn.id).one().position_id == wrong.id


def test_undo_skips_when_position_changed(db, ledger):
    """期间补录了卖出（份额变了）→ 跳过并给原因，绝不抹掉后来的业务事实。"""
    txn, wrong = _mk_mislink(db, ledger.id)
    data = svc.fix_mislink(db, _FAMILY, [txn.id], confirm=True)
    pos = db.query(Position).filter_by(id=data['position_id']).one()
    pos.quantity = Money.shares_to_min_unit(5)
    db.flush()

    result = svc.undo_mislink(db, _FAMILY, data['log_id'])

    assert result['skipped'] == 1 and result['restored'] == 0
    assert '已被改动' in result['skip_reason']
    assert db.query(Position).filter_by(id=data['position_id']).first() is not None
    assert db.query(Transaction).filter_by(id=txn.id).one().position_id == data['position_id']
    assert db.query(AdjustmentLog).filter_by(action=svc.ACTION_MISLINK_UNDO).count() == 1


def test_undo_rejects_foreign_or_wrong_log(db, ledger):
    """只能撤销本家庭的 ``dangling_ref_mislink`` 日志；别的 action / 别的家庭一律拒绝。"""
    txn, _ = _mk_mislink(db, ledger.id)
    data = svc.fix_mislink(db, _FAMILY, [txn.id], confirm=True)

    with pytest.raises(ValueError, match='撤销记录不存在'):
        svc.undo_mislink(db, _OTHER_FAMILY, data['log_id'])

    other_log = AdjustmentLog(family_id=_FAMILY, action='dangling_ref_rebuild', before_json='[]', after_json='{}')
    db.add(other_log)
    db.flush()
    with pytest.raises(ValueError, match='撤销记录不存在'):
        svc.undo_mislink(db, _FAMILY, other_log.id)

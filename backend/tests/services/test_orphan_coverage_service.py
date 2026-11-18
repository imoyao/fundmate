# -*- coding: utf-8 -*-
"""#3089 归置服务：只改一列、整体校验零写入、可撤销、家庭隔离。

与 #2875 `test_orphan_ledger_service.py` 同构：直接把 `db` fixture 的 Session 传给
纯业务函数，不依赖 Flask / 不碰真库。
"""

import json

import pytest

from app.domains.ledgers.models import Ledger
from app.domains.reconciliation.models import AdjustmentLog
from app.domains.transactions.models import Transaction
from app.services import orphan_coverage_service as svc
from app.services.summary_service import _ORPHAN_FLOW_ASSET_TYPES, ORPHAN_FLOW_ASSET_TYPES

_FAMILY = 1


@pytest.fixture
def ledger(db):
    lg = Ledger(name='银河证券', ledger_type='fund', family_id=_FAMILY)
    db.add(lg)
    db.flush()
    return lg


@pytest.fixture
def position(db, make_position):
    return make_position(symbol='MF001', name='银河水星现金添利', quantity=1000, avg_price=1.0, asset_type='fund')


def _orphan(make_transaction, ledger_id, amount_yuan=100, **kwargs):
    return make_transaction(
        None,
        ledger_id,
        txn_type=kwargs.pop('txn_type', 'buy'),
        amount=amount_yuan,
        asset_type=kwargs.pop('asset_type', 'money_fund'),
        entry_status='orphan',
        **kwargs,
    )


def test_asset_type_constant_shares_single_truth():
    """归置判据的资产类型不得与四处口径分叉。"""
    assert ORPHAN_FLOW_ASSET_TYPES == _ORPHAN_FLOW_ASSET_TYPES


def test_cover_only_updates_covered_position_id(db, make_transaction, ledger, position):
    """归置只写 covered_position_id，金额/类型/账本/position_id 原样保留。"""
    a = _orphan(make_transaction, ledger.id, 100)
    b = _orphan(make_transaction, ledger.id, 10, txn_type='dividend')
    snapshot = {t.id: (t.amount, t.asset_type, t.ledger_id, t.position_id) for t in (a, b)}

    result = svc.cover_orphan_flows(db, _FAMILY, [a.id, b.id], position.id, reason='同一笔钱两处记账')

    assert result['updated'] == 2
    assert result['covered_position_id'] == position.id
    assert result['position_name'] == '银河水星现金添利'
    # buy 100 进本金桶、dividend 10 进收益桶：总资产少 110 元（修正，不是丢钱）
    assert result['excluded_net_amount'] == 100.0
    assert result['excluded_income_amount'] == 10.0
    assert result['excluded_total_amount'] == 110.0
    assert a.covered_position_id == position.id and b.covered_position_id == position.id
    for t in (a, b):
        assert (t.amount, t.asset_type, t.ledger_id, t.position_id) == snapshot[t.id]
    log = db.query(AdjustmentLog).filter(AdjustmentLog.id == result['log_id']).one()
    assert log.action == svc.ACTION_COVER
    assert json.loads(log.before_json) == [
        {'id': a.id, 'covered_position_id': None},
        {'id': b.id, 'covered_position_id': None},
    ]
    assert json.loads(log.after_json) == [
        {'id': a.id, 'covered_position_id': position.id},
        {'id': b.id, 'covered_position_id': position.id},
    ]


def test_undo_cover_is_idempotent(db, make_transaction, ledger, position):
    """撤销清空该列即回到原状；重复撤销 restored=0，且每次留痕。"""
    a = _orphan(make_transaction, ledger.id, 100)
    result = svc.cover_orphan_flows(db, _FAMILY, [a.id], position.id)

    first = svc.undo_cover(db, _FAMILY, result['log_id'])
    assert first == {'restored': 1, 'skipped': 0, 'log_id': result['log_id']}
    assert a.covered_position_id is None
    second = svc.undo_cover(db, _FAMILY, result['log_id'])
    assert second['restored'] == 0 and second['skipped'] == 1
    assert db.query(AdjustmentLog).filter(AdjustmentLog.action == svc.ACTION_UNCOVER).count() == 2


def test_undo_skips_row_changed_after_cover(db, make_transaction, ledger, position):
    """归置后又被改成别的持仓 ⇒ 撤销不覆盖别人的操作。"""
    a = _orphan(make_transaction, ledger.id, 100)
    result = svc.cover_orphan_flows(db, _FAMILY, [a.id], position.id)
    a.covered_position_id = position.id + 999
    db.flush()

    out = svc.undo_cover(db, _FAMILY, result['log_id'])
    assert out['restored'] == 0 and out['skipped'] == 1
    assert a.covered_position_id == position.id + 999


@pytest.mark.parametrize('bad', [None, [], '1', [True], [1.5], [1] * 501])
def test_invalid_transaction_ids_rejected(db, make_transaction, ledger, position, bad):
    a = _orphan(make_transaction, ledger.id, 100)
    with pytest.raises(ValueError):
        svc.cover_orphan_flows(db, _FAMILY, bad, position.id)
    assert a.covered_position_id is None


@pytest.mark.parametrize('bad', [None, 0, -1, True, '3', 1.5])
def test_invalid_position_id_rejected(db, make_transaction, ledger, position, bad):
    a = _orphan(make_transaction, ledger.id, 100)
    with pytest.raises(ValueError):
        svc.cover_orphan_flows(db, _FAMILY, [a.id], bad)
    assert a.covered_position_id is None


def test_rejects_batch_if_any_row_is_not_an_uncovered_orphan(db, make_transaction, ledger, position):
    """任一 id 不满足完整口径 ⇒ 整体拒绝、零写入（不写半批）。"""
    good = _orphan(make_transaction, ledger.id, 100)
    attached = _orphan(make_transaction, ledger.id, 100)
    attached.position_id = position.id
    wrong_type = _orphan(make_transaction, ledger.id, 100, asset_type='stock')
    already = _orphan(make_transaction, ledger.id, 100, covered_position_id=position.id)
    db.flush()
    with pytest.raises(ValueError):
        svc.cover_orphan_flows(db, _FAMILY, [good.id, attached.id], position.id)
    with pytest.raises(ValueError):
        svc.cover_orphan_flows(db, _FAMILY, [good.id, wrong_type.id], position.id)
    with pytest.raises(ValueError):
        svc.cover_orphan_flows(db, _FAMILY, [good.id, already.id], position.id)
    covered_ids = [t.id for t in db.query(Transaction).all() if t.covered_position_id is not None]
    assert covered_ids == [already.id], '校验失败不得写出半批归置'


def test_rejects_cross_family_position_and_txn(db, make_transaction, make_position, ledger, position):
    """持仓或流水属于别家 ⇒ 拒绝，不得把归置跨家庭写出去。"""
    other_pos = make_position(symbol='OTHER', name='别家的', family_id=2, quantity=1, avg_price=1.0)
    a = _orphan(make_transaction, ledger.id, 100)
    with pytest.raises(ValueError, match='持仓不存在或不属于当前家庭'):
        svc.cover_orphan_flows(db, _FAMILY, [a.id], other_pos.id)
    assert a.covered_position_id is None

    other_txn = _orphan(make_transaction, ledger.id, 100)
    other_txn.family_id = 2
    db.flush()
    with pytest.raises(ValueError):
        svc.cover_orphan_flows(db, _FAMILY, [a.id, other_txn.id], position.id)
    assert a.covered_position_id is None and other_txn.covered_position_id is None


def test_undo_rejects_unrelated_log(db, ledger):
    """撤销只认 orphan_flow_cover 日志，别的 action 不许拿来清归置。"""
    log = AdjustmentLog(family_id=_FAMILY, action='orphan_ledger_backfill', before_json='[]', after_json='[]')
    db.add(log)
    db.flush()
    with pytest.raises(ValueError):
        svc.undo_cover(db, _FAMILY, log.id)
    with pytest.raises(ValueError):
        svc.undo_cover(db, _FAMILY, True)

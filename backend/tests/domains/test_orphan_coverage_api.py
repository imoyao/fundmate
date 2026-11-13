# -*- coding: utf-8 -*-
"""#3089 归置 / 撤销 HTTP 契约：200 回显、400 整体拒绝、撤销可回到原状。"""

from app.domains.transactions.models import Transaction


def _seed(db, make_transaction, make_position, *, family_id=1):
    pos = make_position(
        symbol='MF001', name='银河水星现金添利', quantity=1000, avg_price=1.0, asset_type='fund', family_id=family_id
    )
    txn = make_transaction(None, None, txn_type='buy', amount=100, asset_type='money_fund', entry_status='orphan')
    db.commit()
    return pos.id, txn.id


def test_cover_then_undo_via_api(client, db, make_transaction, make_position):
    pos_id, txn_id = _seed(db, make_transaction, make_position)
    resp = client.post(
        '/api/reconciliation/orphan-coverage/',
        json={'transaction_ids': [txn_id], 'covered_position_id': pos_id, 'reason': '同一笔钱两处记账'},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()['data']
    assert data['updated'] == 1
    assert data['excluded_total_amount'] == 100.0
    assert '不再算两遍' in resp.get_json()['message']

    db.expire_all()
    assert db.query(Transaction).get(txn_id).covered_position_id == pos_id

    undo = client.post('/api/reconciliation/orphan-coverage/undo/', json={'log_id': data['log_id']})
    assert undo.status_code == 200
    assert undo.get_json()['data']['restored'] == 1
    db.expire_all()
    assert db.query(Transaction).get(txn_id).covered_position_id is None


def test_invalid_batch_returns_400_without_writing(client, db, make_transaction, make_position):
    pos_id, txn_id = _seed(db, make_transaction, make_position)
    resp = client.post(
        '/api/reconciliation/orphan-coverage/',
        json={'transaction_ids': [txn_id, 999999], 'covered_position_id': pos_id},
    )
    assert resp.status_code == 400
    db.expire_all()
    assert db.query(Transaction).get(txn_id).covered_position_id is None


def test_cross_family_position_returns_400(client, db, make_transaction, make_position):
    other_pos_id, txn_id = _seed(db, make_transaction, make_position, family_id=2)
    resp = client.post(
        '/api/reconciliation/orphan-coverage/',
        json={'transaction_ids': [txn_id], 'covered_position_id': other_pos_id},
    )
    assert resp.status_code == 400


def test_undo_rejects_unknown_log(client, db):
    resp = client.post('/api/reconciliation/orphan-coverage/undo/', json={'log_id': 999999})
    assert resp.status_code == 400

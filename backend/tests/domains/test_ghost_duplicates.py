# -*- coding: utf-8 -*-
"""#1066 回归：family 级幽灵重复（跨账本疑似重复交易）扫描。"""

from datetime import date, datetime

from app.domains.ledgers.models import Ledger
from app.domains.summary.views import scan_cross_ledger_duplicates
from app.domains.transactions.models import Transaction

_CDATE = date(2026, 8, 1)
_CDTIME = datetime(2026, 8, 1)


_hash_seq = 0


def _mk_txn(
    db, ledger_id, family_id, symbol='000001', confirm_date=_CDATE, txn_type='buy', amount=100000, status='success'
):
    global _hash_seq
    _hash_seq += 1
    t = Transaction(
        ledger_id=ledger_id,
        family_id=family_id,
        account_name='券商',
        symbol=symbol,
        txn_type=txn_type,
        quantity=100,
        price=100000,  # 分
        fee=0,
        amount=amount,  # 分
        confirm_date=confirm_date,
        trade_date=_CDTIME,
        import_hash=f'txn-{ledger_id}-{symbol}-{confirm_date}-{_hash_seq}',
        status=status,
    )
    db.add(t)
    return t


def test_cross_ledger_duplicate_detected(db):
    """同内容指纹落在 >=2 个 ledger -> 被扫描出来。"""
    ledger_a = Ledger(name='券商A', ledger_type='stock', family_id=1)
    ledger_b = Ledger(name='券商B', ledger_type='stock', family_id=1)
    db.add_all([ledger_a, ledger_b])
    db.flush()

    # 同一笔交易（相同 confirm_date/symbol/txn_type/amount）出现在两个 ledger
    _mk_txn(db, ledger_a.id, 1)
    _mk_txn(db, ledger_b.id, 1)
    db.commit()

    result = scan_cross_ledger_duplicates(db, 1)
    assert len(result) == 1
    grp = result[0]
    assert set(grp['ledger_ids']) == {ledger_a.id, ledger_b.id}
    assert set(grp['ledger_names']) == {'券商A', '券商B'}
    assert grp['count'] == 2
    assert grp['symbol'] == '000001'


def test_same_ledger_not_flagged(db):
    """同一 ledger 内的重复不报（那是幂等去重范畴，非幽灵重复）。"""
    ledger_a = Ledger(name='券商A', ledger_type='stock', family_id=1)
    db.add(ledger_a)
    db.flush()
    _mk_txn(db, ledger_a.id, 1)
    _mk_txn(db, ledger_a.id, 1)  # 同 ledger 同内容
    db.commit()

    result = scan_cross_ledger_duplicates(db, 1)
    assert result == []


def test_distinct_content_not_flagged(db):
    """内容不同（金额不同）即使跨 ledger 也不报。"""
    ledger_a = Ledger(name='券商A', ledger_type='stock', family_id=1)
    ledger_b = Ledger(name='券商B', ledger_type='stock', family_id=1)
    db.add_all([ledger_a, ledger_b])
    db.flush()
    _mk_txn(db, ledger_a.id, 1, amount=100000)
    _mk_txn(db, ledger_b.id, 1, amount=200000)  # 金额不同
    db.commit()

    result = scan_cross_ledger_duplicates(db, 1)
    assert result == []


def test_excludes_shadow_and_non_success(db):
    """影子记录（ledger_id NULL）与未成功交易不参与扫描。"""
    ledger_a = Ledger(name='券商A', ledger_type='stock', family_id=1)
    ledger_b = Ledger(name='券商B', ledger_type='stock', family_id=1)
    db.add_all([ledger_a, ledger_b])
    db.flush()
    # 一条正常跨 ledger 重复
    _mk_txn(db, ledger_a.id, 1)
    _mk_txn(db, ledger_b.id, 1)
    # 影子记录（ledger_id=None）同内容，不应扩大 ledger 集合
    shadow = Transaction(
        ledger_id=None,
        family_id=1,
        account_name='券商',
        symbol='000001',
        txn_type='buy',
        quantity=100,
        price=100000,
        fee=0,
        amount=100000,
        confirm_date=_CDATE,
        trade_date=_CDTIME,
        import_hash='shadow-1',
        status='success',
    )
    db.add(shadow)
    # 一条未成功交易，不应参与
    _mk_txn(db, ledger_a.id, 1, status='pending')
    db.commit()

    result = scan_cross_ledger_duplicates(db, 1)
    assert len(result) == 1
    assert set(result[0]['ledger_ids']) == {ledger_a.id, ledger_b.id}


def test_ghost_duplicates_endpoint_envelope(client, db):
    """#1075 review：GET /api/summary/ghost-duplicates/ 使用标准信封 {data, message}，不使用 {code: 200}。"""
    ledger_a = Ledger(name='券商A', ledger_type='stock', family_id=1)
    ledger_b = Ledger(name='券商B', ledger_type='stock', family_id=1)
    db.add_all([ledger_a, ledger_b])
    db.flush()
    _mk_txn(db, ledger_a.id, 1)
    _mk_txn(db, ledger_b.id, 1)
    db.commit()

    resp = client.get('/api/summary/ghost-duplicates/')
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'code' not in body  # 非标准 {code: 200} 信封不得出现
    assert body['message'] == 'ok'
    data = body['data']
    assert len(data) == 1
    assert data[0]['count'] == 2
    assert set(data[0]['ledger_names']) == {'券商A', '券商B'}

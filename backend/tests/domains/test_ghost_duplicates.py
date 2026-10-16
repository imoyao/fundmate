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


# ---------------------------------------------------------------------------
# #2151 域 D：指纹、身份归一、忽略/撤销与端点
# ---------------------------------------------------------------------------


def _mk_ledgers(db):
    a = Ledger(name='券商A', ledger_type='stock', family_id=1)
    b = Ledger(name='券商B', ledger_type='stock', family_id=1)
    db.add_all([a, b])
    db.flush()
    return a, b


def test_fingerprint_stable_and_ledger_set_sensitive(db):
    """指纹稳定；账本集合变化 ⇒ 新指纹（否则「第 3 家又导入」会被旧忽略静默吞掉）。"""
    from app.services.summary_service import build_ghost_fingerprint

    f_ab = build_ghost_fingerprint(_CDATE, 'EXCHANGE:SH600519', 'buy', 100000, [1, 2])
    # 账本集合顺序无关
    assert build_ghost_fingerprint(_CDATE, 'EXCHANGE:SH600519', 'buy', 100000, [2, 1]) == f_ab
    # 账本集合变化 → 新指纹
    assert build_ghost_fingerprint(_CDATE, 'EXCHANGE:SH600519', 'buy', 100000, [1, 2, 3]) != f_ab


def test_scan_returns_fingerprint_and_transactions(db):
    """扫描结果带 fingerprint / symbol_identity / 组内明细（域 D 渲染与忽略定位都要用）。"""
    a, b = _mk_ledgers(db)
    _mk_txn(db, a.id, 1)
    _mk_txn(db, b.id, 1)
    db.commit()

    grp = scan_cross_ledger_duplicates(db, 1)[0]
    assert len(grp['fingerprint']) == 64
    assert grp['symbol_identity']  # 非空（本用例 symbol 为 6 位数字，无 asset_type → NO_VENUE:000001）
    assert len(grp['transactions']) == 2
    assert {t['ledger_id'] for t in grp['transactions']} == {a.id, b.id}
    assert all(t['ledger_name'] for t in grp['transactions'])


def test_symbol_writing_variants_grouped_together(db):
    """#2151 修复的漏报：同一标的的不同写法（SH600519 / sh600519）应归为一组。

    此前按字面量 `symbol` 分组，两种写法各成一组、各自只有 1 个账本 → `having >= 2` 过滤掉，
    整组重复**静默消失**。归一后它们必须被检出。
    """
    a, b = _mk_ledgers(db)
    _mk_txn(db, a.id, 1, symbol='SH600519')
    _mk_txn(db, b.id, 1, symbol='sh600519')
    db.commit()

    result = scan_cross_ledger_duplicates(db, 1)
    assert len(result) == 1
    assert set(result[0]['ledger_ids']) == {a.id, b.id}


def test_ignore_hides_group_and_undo_restores(db):
    """忽略后组从列表消失；撤销后回来（可撤销闭环）。"""
    from app.services.ghost_duplicate_service import ignore_group, scan_visible_groups, undo_ignore

    a, b = _mk_ledgers(db)
    _mk_txn(db, a.id, 1)
    _mk_txn(db, b.id, 1)
    db.commit()

    fp = scan_visible_groups(db, 1)[0]['fingerprint']
    ignore_group(db, 1, fp, reason='确认是我自己导重了')
    db.commit()
    assert scan_visible_groups(db, 1) == []

    assert undo_ignore(db, 1, fp) is True
    db.commit()
    assert len(scan_visible_groups(db, 1)) == 1


def test_ignore_is_idempotent(db):
    """重复忽略同一指纹不报错、不重复写（前端刷新 / 重放安全）。"""
    from app.services.ghost_duplicate_service import ignore_group

    first = ignore_group(db, 1, 'x' * 64, reason=None)
    second = ignore_group(db, 1, 'x' * 64, reason=None)
    db.commit()
    assert first['created'] is True
    assert second['created'] is False
    assert first['id'] == second['id']


def test_ignore_scope_is_per_family(db):
    """忽略记录按 family 隔离：B 家庭忽略不影响 A 家庭的可见组。"""
    from app.services.ghost_duplicate_service import ignore_group, scan_visible_groups

    # family 1 的重复组
    a, b = _mk_ledgers(db)
    _mk_txn(db, a.id, 1)
    _mk_txn(db, b.id, 1)
    # family 2 的同内容重复组
    c = Ledger(name='券商C', ledger_type='stock', family_id=2)
    d = Ledger(name='券商D', ledger_type='stock', family_id=2)
    db.add_all([c, d])
    db.flush()
    _mk_txn(db, c.id, 2)
    _mk_txn(db, d.id, 2)
    db.commit()

    fp = scan_visible_groups(db, 1)[0]['fingerprint']
    ignore_group(db, 1, fp)
    db.commit()
    assert scan_visible_groups(db, 1) == []
    assert len(scan_visible_groups(db, 2)) == 1


def test_ignore_rejects_above_cap(db):
    """忽略记录写侧封顶：超限抛 ValueError（由视图转 400），不静默丢弃。"""
    from app.services.ghost_duplicate_service import MAX_IGNORES_PER_FAMILY, ignore_group

    for i in range(MAX_IGNORES_PER_FAMILY):
        ignore_group(db, 1, f'{i:064d}')
    db.commit()
    try:
        ignore_group(db, 1, 'f' * 64)
    except ValueError as e:
        assert '上限' in str(e)
    else:
        raise AssertionError('超限时必须报错，不得静默丢弃')


def test_ghost_duplicate_endpoints_flow(client, db):
    """端点闭环：列表 → 忽略 → 列表空 → 已忽略清单 → 撤销 → 列表恢复。"""
    a, b = _mk_ledgers(db)
    _mk_txn(db, a.id, 1)
    _mk_txn(db, b.id, 1)
    db.commit()

    body = client.get('/api/reconciliation/ghost-duplicates/').get_json()
    assert body['message'] == 'ok'
    assert len(body['data']['groups']) == 1
    assert body['data']['ignored_count'] == 0
    fp = body['data']['groups'][0]['fingerprint']

    resp = client.post(f'/api/reconciliation/ghost-duplicates/{fp}/ignore/', json={'reason': '导重了'})
    assert resp.status_code == 200
    assert resp.get_json()['data']['created'] is True

    body = client.get('/api/reconciliation/ghost-duplicates/').get_json()
    assert body['data']['groups'] == []
    assert body['data']['ignored_count'] == 1

    ignored = client.get('/api/reconciliation/ghost-duplicates/ignored/').get_json()['data']
    assert len(ignored) == 1
    assert ignored[0]['fingerprint'] == fp
    assert ignored[0]['reason'] == '导重了'
    assert ignored[0]['ledger_names'] == ['券商A', '券商B']

    resp = client.delete(f'/api/reconciliation/ghost-duplicates/ignored/{ignored[0]["id"]}/')
    assert resp.status_code == 200
    assert resp.get_json()['data']['deleted'] is True

    body = client.get('/api/reconciliation/ghost-duplicates/').get_json()
    assert len(body['data']['groups']) == 1


def test_ignore_endpoint_rejects_non_dict_body(client, db):
    """非 JSON 对象请求体 → 400（与既有 ignore 端点同判据）。"""
    resp = client.post('/api/reconciliation/ghost-duplicates/' + 'a' * 64 + '/ignore/', json=['x'])
    assert resp.status_code == 400


def test_undo_missing_ignore_is_idempotent(client, db):
    """撤销一个不存在的忽略 → deleted=False（不报 404，用户意图已达成）。"""
    resp = client.delete('/api/reconciliation/ghost-duplicates/ignored/99999/')
    assert resp.status_code == 200
    assert resp.get_json()['data']['deleted'] is False


def test_ghost_endpoints_use_standard_envelope(client, db):
    """错误信封：非 2xx 响应必须带 error_code（#1610 契约）。"""
    resp = client.post('/api/reconciliation/ghost-duplicates/' + 'a' * 64 + '/ignore/', json=['x'])
    body = resp.get_json()
    assert 'code' not in body
    assert 'error_code' in body

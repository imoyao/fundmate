# -*- coding: utf-8 -*-
"""#2866 后续：悬空流水「补全信息 / 显式删除」服务的单元测试。

复用仓库既有 ``db`` fixture（临时文件库 + autouse clean_db），直接把 Session 传给纯业务
函数，与视图 ``with user_session() as db:`` 的单事务同构，全程不依赖 Flask / 不碰真库。

日期一律用固定 ``datetime(2026, 11, 7, ...)``，不用 ``date.today()``（跨午夜 flaky）。
金额 / 份额经 ``Money`` 走「分 / 最小单位」写入，断言时换算成「元 / 份」。
"""

import json
from datetime import datetime

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.reconciliation.models import AdjustmentLog
from app.domains.transactions.models import Transaction
from app.services import dangling_ref_remediation_service as svc

_FAMILY = 1
_OTHER_FAMILY = 2
_DANGLING_PID = 990001  # 不存在的持仓 id（position_id 无外键，可安全写入）
_BASE = datetime(2026, 11, 7, 9, 30, 0)  # 固定 created_at / updated_at
_EXISTING_TRADE = datetime(2026, 11, 7, 14, 0, 0)  # 固定已有 trade_date
_DATE_STR = '2026-11-07'  # 补全用的合法日期字符串
_NEW_SYMBOL = '600519'


@pytest.fixture
def ledger(db):
    lg = Ledger(name='2866-补全测试账户', ledger_type='bank', family_id=_FAMILY)
    db.add(lg)
    db.flush()
    return lg


@pytest.fixture
def ledger2(db):
    lg = Ledger(name='2866-补全第二账户', ledger_type='bank', family_id=_FAMILY)
    db.add(lg)
    db.flush()
    return lg


def _mk_pos(db, ledger_id, symbol, shares, *, family_id=_FAMILY, ownership_status='active'):
    """按「份」建现存持仓。cleared 行必须 quantity=0（模型 CHECK 约束）。"""
    qty = Money.shares_to_min_unit(0 if ownership_status == 'cleared' else shares)
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
        ownership_status=ownership_status,
    )
    db.add(p)
    db.flush()
    return p


def _mk_txn(
    db,
    ledger_id,
    *,
    position_id=_DANGLING_PID,
    family_id=_FAMILY,
    symbol='000001',
    asset_type='stock',
    txn_type='buy',
    shares=1.0,
    amount_cents=10000,
    realized_pnl_cents=0,
    created_at=None,
    updated_at=None,
    trade_date=None,
    is_income=None,
):
    """建一条流水。position_id 默认指向不存在的持仓（悬空）；symbol_norm 交给 mapper 事件。"""
    t = Transaction(
        family_id=family_id,
        position_id=position_id,
        ledger_id=ledger_id,
        symbol=symbol,
        asset_type=asset_type,
        txn_type=txn_type,
        quantity=Money.shares_to_min_unit(shares),
        price=Money.yuan_to_price_units(1.0),
        amount=amount_cents,
        realized_pnl=realized_pnl_cents,
        status='success',
        is_income=is_income,
        trade_date=trade_date,
        created_at=created_at if created_at is not None else _BASE,
        updated_at=updated_at if updated_at is not None else _BASE,
    )
    db.add(t)
    db.flush()
    return t


def _snapshot_txns(db, ids):
    rows = db.query(Transaction).filter(Transaction.id.in_(ids)).all()
    return {t.id: (t.symbol, t.trade_date, t.position_id, t.symbol_norm, t.amount, t.quantity) for t in rows}


def _assert_rejected(db, watch_ids, fn, match):
    """整体抛 ValueError 且零写入：无未决写入、无新日志、无增删、watch 行一字不变。"""
    before = _snapshot_txns(db, watch_ids)
    logs_before = db.query(AdjustmentLog).count()
    txn_count_before = db.query(Transaction).count()
    with pytest.raises(ValueError, match=match):
        fn()
    assert not db.new and not db.dirty and not db.deleted, '拒绝分支不得留下未决写入'
    assert db.query(AdjustmentLog).count() == logs_before, '拒绝分支不得写审计日志'
    assert db.query(Transaction).count() == txn_count_before, '拒绝分支不得增删流水'
    assert _snapshot_txns(db, watch_ids) == before, '拒绝分支不得改动任何流水'


def _log_rows(raw):
    """审计 JSON 取逐条列表：允许裸列表或 {'transactions': [...]} 包装。"""
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get('transactions', data.get('rows', []))
    assert isinstance(data, list), f'审计 JSON 应为逐条列表，实为 {type(data).__name__}'
    return data


def _mk_enrich_log(db, *, family_id=_FAMILY, action='dangling_ref_enrich', before_json='[]', after_json='[]'):
    log = AdjustmentLog(
        family_id=family_id,
        action=action,
        before_json=before_json,
        after_json=after_json,
    )
    db.add(log)
    db.flush()
    return log


def _seed_enrichable(db, ledger_id):
    return _mk_txn(db, ledger_id, symbol='', trade_date=None, asset_type='stock')


# ── preview_enrichment：纯只读 / 计数 / 候选持仓 ────────────────────────────


def test_preview_enrichment_is_strictly_readonly(db, ledger):
    """preview 纯只读：库里 symbol / trade_date / symbol_norm 一字不变，不写日志。"""
    t1 = _seed_enrichable(db, ledger.id)
    t2 = _mk_txn(db, ledger.id, symbol='000001', trade_date=_EXISTING_TRADE)
    orig = {t.id: (t.symbol, t.trade_date, t.symbol_norm) for t in (t1, t2)}

    data = svc.preview_enrichment(db, _FAMILY, [t1.id, t2.id], symbol=_NEW_SYMBOL, trade_date=_DATE_STR)

    assert data['txn_count'] == 2
    assert db.query(AdjustmentLog).count() == 0
    for tid, expected in orig.items():
        r = db.query(Transaction).filter_by(id=tid).one()
        assert (r.symbol, r.trade_date, r.symbol_norm) == expected


def test_preview_enrichment_changes_and_counts(db, ledger):
    """changes 的 before/after、fill_*_count、unchanged_count、asset_type 都精确对齐。"""
    t1 = _mk_txn(db, ledger.id, symbol='', trade_date=None, asset_type='stock')
    t2 = _mk_txn(db, ledger.id, symbol='000001', trade_date=None, asset_type='bond')
    t3 = _mk_txn(db, ledger.id, symbol='', trade_date=_EXISTING_TRADE, asset_type='fund')
    t4 = _mk_txn(db, ledger.id, symbol='000002', trade_date=_EXISTING_TRADE, asset_type='stock')
    ids = [t1.id, t2.id, t3.id, t4.id]

    data = svc.preview_enrichment(db, _FAMILY, ids, symbol=_NEW_SYMBOL, trade_date=_DATE_STR)

    assert data['txn_count'] == 4
    assert data['fill_symbol_count'] == 2  # t1 / t3 缺 symbol
    assert data['fill_date_count'] == 2  # t1 / t2 缺 trade_date
    assert data['unchanged_count'] == 1  # t4 两字段都已填
    assert data['symbol'] == _NEW_SYMBOL
    assert '2026-11-07' in str(data['trade_date'])
    assert isinstance(data['warnings'], list) and data['warnings']

    ch = {c['id']: c for c in data['changes']}
    assert set(ch) == set(ids)
    assert (ch[t1.id]['symbol_before'] or '') == ''
    assert ch[t1.id]['symbol_after'] == _NEW_SYMBOL
    assert ch[t1.id]['trade_date_before'] is None
    assert '2026-11-07' in str(ch[t1.id]['trade_date_after'])
    assert ch[t1.id]['asset_type'] == 'stock'
    assert ch[t2.id]['symbol_before'] == ch[t2.id]['symbol_after'] == '000001'
    assert ch[t2.id]['trade_date_before'] is None
    assert '2026-11-07' in str(ch[t2.id]['trade_date_after'])
    assert (ch[t3.id]['symbol_before'] or '') == ''
    assert ch[t3.id]['symbol_after'] == _NEW_SYMBOL
    assert '2026-11-07' in str(ch[t3.id]['trade_date_before'])
    assert ch[t3.id]['trade_date_after'] == ch[t3.id]['trade_date_before']
    assert ch[t4.id]['symbol_before'] == ch[t4.id]['symbol_after'] == '000002'
    assert ch[t4.id]['trade_date_before'] == ch[t4.id]['trade_date_after']


def test_preview_enrichment_candidate_positions_scope(db, ledger, ledger2):
    """candidate_positions 只列同账本 + 同新标的 + 本 family 的现存持仓，数量 ≤20、份额是份。"""
    gid, g2id = ledger.id, ledger2.id
    t1 = _seed_enrichable(db, gid)
    p_match = _mk_pos(db, gid, _NEW_SYMBOL, 2.0)
    p_other_symbol = _mk_pos(db, gid, '000002', 1.0)
    p_other_ledger = _mk_pos(db, g2id, _NEW_SYMBOL, 1.0)
    p_other_family = _mk_pos(db, None, _NEW_SYMBOL, 1.0, family_id=_OTHER_FAMILY)

    data = svc.preview_enrichment(db, _FAMILY, [t1.id], symbol=_NEW_SYMBOL, trade_date=_DATE_STR)

    cands = data['candidate_positions']
    assert len(cands) <= 20
    ids = [c['id'] for c in cands]
    assert ids == [p_match.id]
    c = cands[0]
    assert c['symbol'] == _NEW_SYMBOL
    assert c['ledger_id'] == gid
    assert c['quantity'] == pytest.approx(2.0)
    assert c['ownership_status'] == 'active'
    assert p_other_symbol.id not in ids
    assert p_other_ledger.id not in ids
    assert p_other_family.id not in ids


def test_reverse_control_no_live_positions_yields_empty_candidates(db, ledger):
    """反向对照：没有任何现存持仓时候选必须为空，证明「非空候选」断言不是恒真。"""
    t1 = _seed_enrichable(db, ledger.id)

    data = svc.preview_enrichment(db, _FAMILY, [t1.id], symbol=_NEW_SYMBOL, trade_date=_DATE_STR)

    assert data['candidate_positions'] == []
    assert data['txn_count'] == 1
    assert data['fill_symbol_count'] == 1


def test_reverse_control_zero_stub_yields_zero_counts_and_amount(db, ledger):
    """反向对照：桩数据全 0（份额/金额/已实现盈亏皆 0、两字段都已填）时，
    fill 计数、total_amount 必须归 0，证明主用例里的正数断言不是恒真。"""
    t1 = _mk_txn(
        db, ledger.id, symbol='000001', trade_date=_EXISTING_TRADE, shares=0.0, amount_cents=0, realized_pnl_cents=0
    )
    t2 = _mk_txn(
        db, ledger.id, symbol='000002', trade_date=_EXISTING_TRADE, shares=0.0, amount_cents=0, realized_pnl_cents=0
    )
    ids = [t1.id, t2.id]

    pe = svc.preview_enrichment(db, _FAMILY, ids, symbol=_NEW_SYMBOL, trade_date=_DATE_STR)
    assert pe['fill_symbol_count'] == 0
    assert pe['fill_date_count'] == 0
    assert pe['unchanged_count'] == pe['txn_count'] == 2

    pd = svc.preview_delete(db, _FAMILY, ids)
    assert pd['txn_count'] == 2
    assert pd['total_amount'] == pytest.approx(0.0)
    for row in pd['transactions']:
        assert row['amount'] == pytest.approx(0.0)
        assert row['quantity'] == pytest.approx(0.0)
        assert row['realized_pnl'] == pytest.approx(0.0)


# ── preview_delete：纯只读 / 单位 / 完整快照口径 ────────────────────────────


def test_preview_delete_is_readonly_with_correct_units(db, ledger):
    """preview_delete 不删行、不写日志；quantity 是份、amount/realized_pnl 是元；快照列 >20。"""
    t1 = _mk_txn(
        db,
        ledger.id,
        symbol=_NEW_SYMBOL,
        trade_date=_EXISTING_TRADE,
        shares=2.0,
        amount_cents=12345,
        realized_pnl_cents=678,
    )
    t2 = _mk_txn(db, ledger.id, symbol='600520', amount_cents=100)
    bystander = _mk_txn(db, ledger.id, symbol='KEEP')
    ids = [t1.id, t2.id]

    data = svc.preview_delete(db, _FAMILY, ids)

    assert data['txn_count'] == 2
    assert data['snapshot_columns'] > 20  # 证明完整行快照口径存在
    assert data['total_amount'] == pytest.approx(124.45)  # (12345 + 100) 分 → 元
    assert isinstance(data['warnings'], list) and data['warnings']
    rows = {r['id']: r for r in data['transactions']}
    assert set(rows) == set(ids)
    r1 = rows[t1.id]
    assert r1['txn_type'] == 'buy'
    assert r1['symbol'] == _NEW_SYMBOL
    assert r1['position_id'] == _DANGLING_PID
    assert r1['quantity'] == pytest.approx(2.0)  # 份
    assert r1['amount'] == pytest.approx(123.45)  # 元
    assert r1['realized_pnl'] == pytest.approx(6.78)  # 元
    assert r1['is_income'] is None
    assert str(r1['trade_date']).startswith('2026-11-07')
    assert rows[t2.id]['trade_date'] is None
    # 纯只读：一行不删、一条日志不写
    assert db.query(Transaction).count() == 3
    assert db.query(AdjustmentLog).count() == 0
    assert db.query(Transaction).filter_by(id=bystander.id).count() == 1


# ── enrich_transactions：只补空字段 / 审计日志 ──────────────────────────────


def test_enrich_fills_only_empty_fields_and_writes_audit_log(db, ledger):
    """只补空字段、已有值绝不覆盖；symbol_norm 由 mapper 重算补完非空；写 enrich 日志。"""
    t1 = _mk_txn(db, ledger.id, symbol='', trade_date=None, asset_type='stock')
    t2 = _mk_txn(db, ledger.id, symbol='000001', trade_date=None, asset_type='stock')
    t3 = _mk_txn(db, ledger.id, symbol='', trade_date=_EXISTING_TRADE, asset_type='stock')
    t4 = _mk_txn(db, ledger.id, symbol='000002', trade_date=_EXISTING_TRADE, asset_type='stock')
    ids = [t1.id, t2.id, t3.id, t4.id]
    orig = {t.id: (t.amount, t.quantity, t.realized_pnl, t.source, t.import_hash) for t in (t1, t2, t3, t4)}
    assert t1.symbol_norm == ''  # 补前由 mapper 算出空串

    ret = svc.enrich_transactions(
        db, _FAMILY, ids, symbol=_NEW_SYMBOL, trade_date=_DATE_STR, reason='人工核对', operator=7, confirm=True
    )

    assert ret['updated'] == 3
    assert ret['skipped'] == 1
    assert ret['updated'] + ret['skipped'] == len(ids)
    assert ret['symbol'] == _NEW_SYMBOL
    assert ret['log_id']

    r1 = db.query(Transaction).filter_by(id=t1.id).one()
    r2 = db.query(Transaction).filter_by(id=t2.id).one()
    r3 = db.query(Transaction).filter_by(id=t3.id).one()
    r4 = db.query(Transaction).filter_by(id=t4.id).one()
    assert r1.symbol == _NEW_SYMBOL
    assert r1.trade_date == datetime(2026, 11, 7, 0, 0, 0)
    assert r1.symbol_norm  # 非空，mapper 事件重算（不手改派生列）
    assert r2.symbol == '000001'  # 已有值绝不覆盖
    assert r2.trade_date == datetime(2026, 11, 7, 0, 0, 0)
    assert r3.symbol == _NEW_SYMBOL
    assert r3.trade_date == _EXISTING_TRADE  # 已有值绝不覆盖
    assert r4.symbol == '000002' and r4.trade_date == _EXISTING_TRADE  # 跳过
    for tid, expected in orig.items():
        r = db.query(Transaction).filter_by(id=tid).one()
        assert (r.amount, r.quantity, r.realized_pnl, r.source, r.import_hash) == expected

    log = db.query(AdjustmentLog).filter_by(action='dangling_ref_enrich').one()
    assert log.family_id == _FAMILY
    assert log.reason == '人工核对'
    assert log.operator == 7
    before = _log_rows(log.before_json)
    after = _log_rows(log.after_json)
    assert all({'id', 'symbol', 'trade_date'} <= set(e) for e in before + after)
    logged_before = {e['id'] for e in before}
    logged_after = {e['id'] for e in after}
    assert logged_before <= set(ids) and logged_after <= set(ids)
    assert {t1.id, t2.id, t3.id} <= logged_before
    assert {t1.id, t2.id, t3.id} <= logged_after
    bm = {e['id']: e for e in before}
    am = {e['id']: e for e in after}
    assert (bm[t1.id]['symbol'] or '') == ''
    assert bm[t1.id]['trade_date'] is None
    assert am[t1.id]['symbol'] == _NEW_SYMBOL
    assert '2026-11-07' in str(am[t1.id]['trade_date'])


# ── enrich_transactions：拒绝分支（每个都断言整体 400 + 零写入）────────────


def test_enrich_rejects_confirm_false(db, ledger):
    t = _seed_enrichable(db, ledger.id)
    _assert_rejected(
        db,
        [t.id],
        lambda: svc.enrich_transactions(db, _FAMILY, [t.id], symbol=_NEW_SYMBOL, confirm=False),
        match='confirm',
    )


@pytest.mark.parametrize('bad', ['true', 1, 0, [], {}])
def test_enrich_rejects_non_bool_confirm(db, ledger, bad):
    t = _seed_enrichable(db, ledger.id)
    _assert_rejected(
        db,
        [t.id],
        lambda: svc.enrich_transactions(db, _FAMILY, [t.id], symbol=_NEW_SYMBOL, confirm=bad),
        match='confirm',
    )


def test_enrich_rejects_overlong_symbol(db, ledger):
    t = _seed_enrichable(db, ledger.id)
    _assert_rejected(
        db,
        [t.id],
        lambda: svc.enrich_transactions(db, _FAMILY, [t.id], symbol='A' * 31, confirm=True),
        match='symbol|30|长度',
    )


@pytest.mark.parametrize('bad', [123, 1.5, [], {'s': 'x'}])
def test_enrich_rejects_non_str_symbol(db, ledger, bad):
    t = _seed_enrichable(db, ledger.id)
    _assert_rejected(
        db,
        [t.id],
        lambda: svc.enrich_transactions(db, _FAMILY, [t.id], symbol=bad, confirm=True),
        match='symbol|字符串',
    )


@pytest.mark.parametrize('bad', ['2026-13-99', 'not-a-date', '2026/11/07'])
def test_enrich_rejects_invalid_trade_date(db, ledger, bad):
    t = _seed_enrichable(db, ledger.id)
    _assert_rejected(
        db,
        [t.id],
        lambda: svc.enrich_transactions(db, _FAMILY, [t.id], trade_date=bad, confirm=True),
        match='trade_date|日期|格式',
    )


def test_enrich_rejects_no_field_provided(db, ledger):
    t = _seed_enrichable(db, ledger.id)
    _assert_rejected(
        db,
        [t.id],
        lambda: svc.enrich_transactions(db, _FAMILY, [t.id], confirm=True),
        match='至少|symbol|trade_date|字段',
    )


def test_enrich_rejects_when_all_rows_already_filled(db, ledger):
    """updated==0（全是已填值）→ 整体拒绝、零写入。"""
    t1 = _mk_txn(db, ledger.id, symbol='000001', trade_date=_EXISTING_TRADE)
    t2 = _mk_txn(db, ledger.id, symbol='000002', trade_date=_EXISTING_TRADE)
    _assert_rejected(
        db,
        [t1.id, t2.id],
        lambda: svc.enrich_transactions(
            db, _FAMILY, [t1.id, t2.id], symbol=_NEW_SYMBOL, trade_date=_DATE_STR, confirm=True
        ),
        match='补全|无需|已填|updated|0',
    )


def test_enrich_rejects_empty_ids(db, ledger):
    t = _seed_enrichable(db, ledger.id)
    _assert_rejected(
        db,
        [t.id],
        lambda: svc.enrich_transactions(db, _FAMILY, [], symbol=_NEW_SYMBOL, confirm=True),
        match='transaction_ids|非空',
    )


def test_enrich_rejects_ids_over_limit(db, ledger):
    t = _seed_enrichable(db, ledger.id)
    too_many = [t.id] * 501
    _assert_rejected(
        db,
        [t.id],
        lambda: svc.enrich_transactions(db, _FAMILY, too_many, symbol=_NEW_SYMBOL, confirm=True),
        match='transaction_ids|500',
    )


def test_enrich_rejects_bool_in_ids(db, ledger):
    t = _seed_enrichable(db, ledger.id)
    _assert_rejected(
        db,
        [t.id],
        lambda: svc.enrich_transactions(db, _FAMILY, [True, t.id], symbol=_NEW_SYMBOL, confirm=True),
        match='transaction_ids|整数',
    )


def test_enrich_rejects_string_in_ids(db, ledger):
    t = _seed_enrichable(db, ledger.id)
    _assert_rejected(
        db,
        [t.id],
        lambda: svc.enrich_transactions(db, _FAMILY, [t.id, 'x'], symbol=_NEW_SYMBOL, confirm=True),
        match='transaction_ids|整数',
    )


def test_enrich_rejects_target_no_longer_dangling(db, ledger):
    """目标流水 position_id 已指向现存持仓（不再悬空）→ 整体拒绝、零写入。"""
    pos = _mk_pos(db, ledger.id, '000001', 1.0)
    fixed = _mk_txn(db, ledger.id, position_id=pos.id, symbol='', trade_date=None)
    _assert_rejected(
        db,
        [fixed.id],
        lambda: svc.enrich_transactions(db, _FAMILY, [fixed.id], symbol=_NEW_SYMBOL, confirm=True),
        match='悬空|家庭|不属于',
    )


def test_enrich_rejects_cross_family_id(db, ledger):
    foreign = _mk_txn(db, ledger.id, symbol='', trade_date=None, family_id=_OTHER_FAMILY)
    _assert_rejected(
        db,
        [foreign.id],
        lambda: svc.enrich_transactions(db, _FAMILY, [foreign.id], symbol=_NEW_SYMBOL, confirm=True),
        match='悬空|家庭|不属于',
    )


# ── undo_enrichment：恢复 / 跳过 / 幂等 / 拒绝 ───────────────────────────────


def test_undo_enrichment_restores_original_values(db, ledger):
    t1 = _mk_txn(db, ledger.id, symbol='', trade_date=None, asset_type='stock')
    t2 = _mk_txn(db, ledger.id, symbol='000001', trade_date=None, asset_type='stock')
    ret = svc.enrich_transactions(db, _FAMILY, [t1.id, t2.id], symbol=_NEW_SYMBOL, trade_date=_DATE_STR, confirm=True)
    assert ret['updated'] == 2
    assert db.query(Transaction).filter_by(id=t1.id).one().symbol_norm  # 补全后非空

    undone = svc.undo_enrichment(db, _FAMILY, ret['log_id'])

    assert undone['restored'] == 2
    assert undone['skipped'] == 0
    assert undone['log_id'] == ret['log_id']
    r1 = db.query(Transaction).filter_by(id=t1.id).one()
    r2 = db.query(Transaction).filter_by(id=t2.id).one()
    assert (r1.symbol or '') == ''
    assert r1.trade_date is None
    assert r1.symbol_norm == ''  # mapper 事件按空 symbol 重算，不留陈旧派生值
    assert r2.symbol == '000001'
    assert r2.trade_date is None
    assert db.query(AdjustmentLog).filter_by(action='dangling_ref_enrich_undo').count() == 1


def test_undo_enrichment_skips_manually_changed_row(db, ledger):
    """仅当当前值仍等于 after 值才恢复：手工改过一行 → skipped，且不影响其它行。"""
    t1 = _mk_txn(db, ledger.id, symbol='', trade_date=None, asset_type='stock')
    t2 = _mk_txn(db, ledger.id, symbol='', trade_date=None, asset_type='stock')
    ret = svc.enrich_transactions(db, _FAMILY, [t1.id, t2.id], symbol=_NEW_SYMBOL, trade_date=_DATE_STR, confirm=True)
    db.query(Transaction).filter_by(id=t2.id).one().symbol = 'MANUAL'
    db.flush()

    undone = svc.undo_enrichment(db, _FAMILY, ret['log_id'])

    assert undone['restored'] == 1
    assert undone['skipped'] >= 1
    assert (db.query(Transaction).filter_by(id=t1.id).one().symbol or '') == ''
    assert db.query(Transaction).filter_by(id=t2.id).one().symbol == 'MANUAL'


def test_undo_enrichment_is_idempotent_and_leaves_trace(db, ledger):
    t1 = _seed_enrichable(db, ledger.id)
    ret = svc.enrich_transactions(db, _FAMILY, [t1.id], symbol=_NEW_SYMBOL, trade_date=_DATE_STR, confirm=True)

    first = svc.undo_enrichment(db, _FAMILY, ret['log_id'])
    assert first['restored'] == 1
    second = svc.undo_enrichment(db, _FAMILY, ret['log_id'])
    assert second['restored'] == 0
    r1 = db.query(Transaction).filter_by(id=t1.id).one()
    assert (r1.symbol or '') == '' and r1.trade_date is None
    assert db.query(AdjustmentLog).filter_by(action='dangling_ref_enrich_undo').count() == 2


def test_undo_enrichment_rejects_non_enrich_log(db, ledger):
    t = _seed_enrichable(db, ledger.id)
    log = _mk_enrich_log(db, action='dangling_ref_delete')
    with pytest.raises(ValueError, match='撤销记录|dangling_ref_enrich|无权'):
        svc.undo_enrichment(db, _FAMILY, log.id)
    assert db.query(AdjustmentLog).filter_by(action='dangling_ref_enrich_undo').count() == 0
    assert (db.query(Transaction).filter_by(id=t.id).one().symbol or '') == ''


def test_undo_enrichment_rejects_cross_family_log(db, ledger):
    log = _mk_enrich_log(
        db,
        family_id=_OTHER_FAMILY,
        before_json=json.dumps([{'id': 1, 'symbol': 'X', 'trade_date': None}]),
        after_json=json.dumps([{'id': 1, 'symbol': 'Y', 'trade_date': None}]),
    )
    with pytest.raises(ValueError, match='撤销记录|dangling_ref_enrich|无权'):
        svc.undo_enrichment(db, _FAMILY, log.id)
    assert db.query(AdjustmentLog).filter_by(action='dangling_ref_enrich_undo').count() == 0


def test_undo_enrichment_rejects_corrupted_json(db, ledger):
    log = _mk_enrich_log(db, before_json='{不是 JSON', after_json='[]')
    with pytest.raises(ValueError, match='JSON|损坏|解析'):
        svc.undo_enrichment(db, _FAMILY, log.id)
    assert db.query(AdjustmentLog).filter_by(action='dangling_ref_enrich_undo').count() == 0


# ── delete_transactions：硬确认 / 物理删除 / 完整行快照 ─────────────────────


def test_delete_rejects_confirm_false(db, ledger):
    t = _mk_txn(db, ledger.id, symbol=_NEW_SYMBOL)
    _assert_rejected(
        db,
        [t.id],
        lambda: svc.delete_transactions(db, _FAMILY, [t.id], confirm=False, confirm_phrase='删除'),
        match='confirm',
    )


@pytest.mark.parametrize('phrase', ['', 'shanchu', None, 'DELETE', '删'])
def test_delete_rejects_wrong_confirm_phrase(db, ledger, phrase):
    t = _mk_txn(db, ledger.id, symbol=_NEW_SYMBOL)
    _assert_rejected(
        db,
        [t.id],
        lambda: svc.delete_transactions(db, _FAMILY, [t.id], confirm=True, confirm_phrase=phrase),
        match='删除|confirm_phrase|确认',
    )


def test_delete_physically_removes_rows_with_full_snapshot(db, ledger):
    """成功时物理删除、写 dangling_ref_delete 日志，before_json 是完整行快照。"""
    t1 = _mk_txn(
        db,
        ledger.id,
        symbol=_NEW_SYMBOL,
        trade_date=_EXISTING_TRADE,
        shares=2.0,
        amount_cents=12345,
        realized_pnl_cents=678,
    )
    t2 = _mk_txn(db, ledger.id, symbol='600520', amount_cents=100)
    bystander = _mk_txn(db, ledger.id, symbol='KEEP')
    ids = [t1.id, t2.id]

    ret = svc.delete_transactions(db, _FAMILY, ids, reason='确认删除', confirm=True, confirm_phrase='删除')

    assert ret['deleted'] == 2
    assert ret['confirm_phrase'] == '删除'
    assert ret['total_amount'] == pytest.approx(124.45)
    assert ret['log_id']
    assert db.query(Transaction).filter(Transaction.id.in_(ids)).count() == 0
    assert db.query(Transaction).filter_by(id=bystander.id).count() == 1

    log = db.query(AdjustmentLog).filter_by(action='dangling_ref_delete').one()
    assert log.family_id == _FAMILY
    assert log.reason == '确认删除'
    before = _log_rows(log.before_json)
    assert len(before) == 2
    assert {row['id'] for row in before} == set(ids)
    for row in before:
        assert {
            'id',
            'txn_type',
            'quantity',
            'amount',
            'family_id',
            'created_at',
            'symbol',
            'position_id',
            'symbol_norm',
        } <= set(row)
        assert 'type' not in row  # 键用 ORM 属性名 txn_type，不是 DB 列名 type
        assert isinstance(row['created_at'], str) and '2026-11-07' in row['created_at']
        assert row['trade_date'] is None or isinstance(row['trade_date'], str)
    after = json.loads(log.after_json)
    assert 'deleted_ids' in after
    assert set(after['deleted_ids']) == set(ids)


# ── undo_delete：按快照恢复 / 跳过占用 id / 幂等 / 拒绝 ─────────────────────


def test_undo_delete_restores_full_row(db, ledger):
    t1 = _mk_txn(db, ledger.id, symbol=_NEW_SYMBOL, trade_date=_EXISTING_TRADE, shares=2.0, amount_cents=12345)
    t2 = _mk_txn(db, ledger.id, symbol='600520', amount_cents=100)
    ids = [t1.id, t2.id]
    orig = {
        t.id: {
            'symbol': t.symbol,
            'position_id': t.position_id,
            'amount': t.amount,
            'created_at': t.created_at,
            'trade_date': t.trade_date,
            'symbol_norm': t.symbol_norm,
        }
        for t in (t1, t2)
    }
    log_id = svc.delete_transactions(db, _FAMILY, ids, confirm=True, confirm_phrase='删除')['log_id']

    undone = svc.undo_delete(db, _FAMILY, log_id)

    assert undone['restored'] == 2
    assert undone['skipped'] == 0
    assert undone['log_id'] == log_id
    for tid, expected in orig.items():
        r = db.query(Transaction).filter_by(id=tid).one()
        assert r.id == tid
        assert r.position_id == expected['position_id']
        assert r.symbol == expected['symbol']
        assert r.amount == expected['amount']
        assert r.created_at == expected['created_at']
        assert r.trade_date == expected['trade_date']
        assert r.symbol_norm == expected['symbol_norm']  # mapper 重算后仍一致
    assert db.query(AdjustmentLog).filter_by(action='dangling_ref_delete_undo').count() == 1


def test_undo_delete_skips_id_reused_by_new_transaction(db, ledger):
    """某 id 已被新流水占用 → skipped，且不覆盖它、不影响其它行的恢复。"""
    ledger_id = ledger.id
    t1 = _mk_txn(db, ledger_id, symbol=_NEW_SYMBOL, amount_cents=100)
    t2 = _mk_txn(db, ledger_id, symbol='600520', amount_cents=200)
    ids = [t1.id, t2.id]
    occupied_id = t1.id
    log_id = svc.delete_transactions(db, _FAMILY, ids, confirm=True, confirm_phrase='删除')['log_id']
    db.flush()
    db.expunge_all()  # 移出已删除实例，避免同 id 新建时 identity map 冲突
    occupied = Transaction(
        id=occupied_id,
        family_id=_FAMILY,
        position_id=_DANGLING_PID,
        ledger_id=ledger_id,
        symbol='NEW',
        asset_type='stock',
        txn_type='buy',
        quantity=Money.shares_to_min_unit(1.0),
        amount=999,
        created_at=_BASE,
        updated_at=_BASE,
    )
    db.add(occupied)
    db.flush()

    undone = svc.undo_delete(db, _FAMILY, log_id)

    assert undone['restored'] == 1
    assert undone['skipped'] >= 1
    assert db.query(Transaction).filter_by(id=occupied_id).one().symbol == 'NEW'
    assert db.query(Transaction).filter_by(id=t2.id).one().symbol == '600520'


def test_undo_delete_is_idempotent_but_leaves_trace(db, ledger):
    t1 = _mk_txn(db, ledger.id, symbol=_NEW_SYMBOL)
    t2 = _mk_txn(db, ledger.id, symbol='600520')
    ids = [t1.id, t2.id]
    log_id = svc.delete_transactions(db, _FAMILY, ids, confirm=True, confirm_phrase='删除')['log_id']

    first = svc.undo_delete(db, _FAMILY, log_id)
    assert first['restored'] == 2
    second = svc.undo_delete(db, _FAMILY, log_id)
    assert second['restored'] == 0
    assert db.query(Transaction).filter(Transaction.id.in_(ids)).count() == 2
    assert db.query(AdjustmentLog).filter_by(action='dangling_ref_delete_undo').count() == 2


def test_undo_delete_rejects_other_action_log(db, ledger):
    t = _mk_txn(db, ledger.id, symbol=_NEW_SYMBOL)
    log = _mk_enrich_log(db, action='dangling_ref_enrich')
    with pytest.raises(ValueError, match='撤销记录|dangling_ref_delete|无权'):
        svc.undo_delete(db, _FAMILY, log.id)
    assert db.query(AdjustmentLog).filter_by(action='dangling_ref_delete_undo').count() == 0
    assert db.query(Transaction).filter_by(id=t.id).count() == 1

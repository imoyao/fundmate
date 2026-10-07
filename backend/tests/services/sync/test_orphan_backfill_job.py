# -*- coding: utf-8 -*-
"""孤儿交易回填 job 测试（#950）。

背景：`tech-debt.md` §1「孤儿交易无自动回填机制」。交易流水与持仓是两条独立写入
路径，导入顺序不保证——先导流水后建持仓时那批流水就成了孤儿（`position_id IS NULL`）。
写入层只在**建仓那一刻**挂回货基/逆回购（#863 口径A），其余标的的孤儿会永久滞留。

本文件钉住三条验收标准 + 几条设计约束：
  1. 定时扫描并按 symbol/family 关联既有持仓；
  2. **只补 `position_id`**，不改写金额/确认日；
  3. 幂等（重复跑不重复关联），并能观测到回填前后的孤儿计数变化。
"""

import datetime as dt

from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.adapters.null_adapter import NullAdapter
from app.services.sync.jobs.orphan_backfill_job import OrphanBackfillJob

DAY = dt.date(2026, 10, 8)


def _job(db) -> OrphanBackfillJob:
    return OrphanBackfillJob(NullAdapter(), db)


def _position(db, symbol, asset_type='stock', ledger_id=1, family_id=1):
    """建持仓。`symbol_norm` 由落库前的事件钩子自动填（#1662），故这里不传。"""
    pos = Position(
        symbol=symbol,
        asset_type=asset_type,
        ledger_id=ledger_id,
        family_id=family_id,
        name=symbol,
    )
    db.add(pos)
    db.commit()
    return pos


def _orphan(
    db,
    symbol,
    asset_type='stock',
    ledger_id=1,
    family_id=1,
    is_income=None,
    amount=100000,
    confirm_date=DAY,
):
    """建一条孤儿流水（position_id 缺省即 NULL）。"""
    txn = Transaction(
        position_id=None,
        symbol=symbol,
        txn_type='buy',
        amount=amount,
        confirm_date=confirm_date,
        trade_date=dt.datetime.combine(confirm_date, dt.time(10, 0)),
        asset_type=asset_type,
        ledger_id=ledger_id,
        family_id=family_id,
        is_income=is_income,
        status='success',
    )
    db.add(txn)
    db.commit()
    return txn


def _orphan_count(db) -> int:
    return db.query(Transaction).filter(Transaction.position_id.is_(None)).count()


# ── 验收 1：扫描并关联既有持仓 ──


def test_attaches_orphan_to_matching_position(db):
    """同 (ledger, family) + 同身份 → 挂回既有持仓。"""
    pos = _position(db, '159915', asset_type='stock')
    txn = _orphan(db, '159915', asset_type='stock')

    result = _job(db).run()

    assert result['status'] == 'success'
    db.refresh(txn)
    assert txn.position_id == pos.id


def test_attaches_by_identity_not_literal_symbol(db):
    """身份口径（#1662）：`sz159915` 与 `SZ159915` 是同一只基金，字面量不同也必须挂上。

    若按字面量相等匹配，这条流水会永远留在孤儿态——正是 #1657复审栽过的坑
    （脚本按 symbol 精确相等，跨形态组合被静默漏挂）。
    """
    pos = _position(db, 'SZ159915', asset_type='stock')
    txn = _orphan(db, 'sz159915', asset_type='stock')

    _job(db).run()

    db.refresh(txn)
    assert txn.position_id == pos.id


def test_attaches_otc_fund_with_surrounding_spaces(db):
    """场外基金码的空格变体同样按身份命中（`symbol_identity` 会 strip + upper）。"""
    pos = _position(db, '004369', asset_type='fund')
    txn = _orphan(db, ' 004369 ', asset_type='fund')

    _job(db).run()

    db.refresh(txn)
    assert txn.position_id == pos.id


# ── 验收 2：只补 position_id，不改金额/确认日 ──


def test_only_fills_position_id_and_leaves_amount_and_date_untouched(db):
    """回填是「补链接」不是「修数据」：金额与确认日必须原样保留。"""
    pos = _position(db, '159915', asset_type='stock')
    other_day = dt.date(2026, 9, 1)
    txn = _orphan(db, '159915', asset_type='stock', amount=123456, confirm_date=other_day)

    _job(db).run()

    db.refresh(txn)
    assert txn.position_id == pos.id
    assert txn.amount == 123456, '金额被改写即为数据污染'
    assert txn.confirm_date == other_day, '确认日被改写即为数据污染'


# ── 验收 3：幂等 + 孤儿计数可观测 ──


def test_orphan_count_drops_and_second_run_is_noop(db):
    """回填前后孤儿计数下降，且第二次跑是no-op（幂等）。"""
    pos = _position(db, '159915', asset_type='stock')
    txn = _orphan(db, '159915', asset_type='stock')
    _orphan(db, '000001', asset_type='stock')  # 无匹配持仓，应留在孤儿态

    before = _orphan_count(db)
    assert before == 2

    first = _job(db).run()
    after_first = _orphan_count(db)

    assert first['stats']['attached'] == 1
    assert after_first == 1, '挂上一条后孤儿数应从 2 降到 1'
    db.refresh(txn)
    assert txn.position_id == pos.id

    second = _job(db).run()
    assert second['stats']['attached'] == 0, '重复跑不得重复关联'
    assert second['stats']['scanned'] == 1
    assert _orphan_count(db) == 1, '孤儿计数不得因重跑而变化'


# ── 宁可不挂，也不挂错 ──


def test_does_not_attach_across_family(db):
    """family 不同 → 不挂（防跨家庭串号）。"""
    _position(db, '159915', asset_type='stock', family_id=1)
    txn = _orphan(db, '159915', asset_type='stock', family_id=2)

    result = _job(db).run()

    db.refresh(txn)
    assert txn.position_id is None
    assert result['stats']['attached'] == 0
    assert result['stats']['no_position'] == 1


def test_does_not_attach_across_ledger(db):
    """ledger 不同 → 不挂（同一家庭两个账户里的同一标的不能混）。"""
    _position(db, '159915', asset_type='stock', ledger_id=1)
    txn = _orphan(db, '159915', asset_type='stock', ledger_id=2)

    result = _job(db).run()

    db.refresh(txn)
    assert txn.position_id is None
    assert result['stats']['no_position'] == 1


def test_skips_ambiguous_candidates_instead_of_guessing(db):
    """`ledger_id IS NULL` 时唯一约束失效，同身份可能有多行 → 跳过而不是随机取一条。

    静默取第一条等于随机挂错：挂错会让持仓的交易史凭空多出别人的流水，
    而孤儿数却下降了——这种错误事后极难发现。
    """
    _position(db, '159915', asset_type='stock', ledger_id=None)
    _position(db, 'sz159915', asset_type='stock', ledger_id=None)  # 同身份、不同字面量
    txn = _orphan(db, 'SZ159915', asset_type='stock', ledger_id=None)

    result = _job(db).run()

    db.refresh(txn)
    assert txn.position_id is None, '候选歧义时必须不挂'
    assert result['stats']['ambiguous'] == 1
    assert result['stats']['attached'] == 0


def test_orphan_without_symbol_is_skipped(db):
    """symbol 为空的流水算不出身份 → 计入 no_identity，且绝不能挂到任意持仓上。"""
    _position(db, '159915', asset_type='stock')
    txn = _orphan(db, None, asset_type='stock')

    result = _job(db).run()

    db.refresh(txn)
    assert txn.position_id is None
    assert result['stats']['no_identity'] == 1


# ── 口径边界 ──


def test_income_rows_are_not_backfilled(db):
    """收益行（is_income）不参与回填，与 #863 `find_orphan_cash_flows` 口径一致。

    收益行属于「孤儿净额」桶语义（income 而非本金流动），挂到持仓上会与那条口径打架。
    """
    pos = _position(db, '159915', asset_type='stock')
    txn = _orphan(db, '159915', asset_type='stock', is_income=True)

    result = _job(db).run()

    db.refresh(txn)
    assert txn.position_id is None
    assert result['stats']['scanned'] == 0, '收益行不该进入扫描集'


def test_already_attached_transaction_is_untouched(db):
    """已有 position_id 的流水不进扫描集（本就不该被本job 改写）。"""
    pos = _position(db, '159915', asset_type='stock')
    other = _position(db, '000001', asset_type='stock')
    txn = _orphan(db, '159915', asset_type='stock')
    txn.position_id = other.id
    db.commit()

    result = _job(db).run()

    db.refresh(txn)
    assert txn.position_id == other.id
    assert result['stats']['scanned'] == 0


def test_empty_library_succeeds(db):
    """没有孤儿是常态而非失败。"""
    result = _job(db).run()

    assert result['status'] == 'success'
    assert result['stats']['scanned'] == 0
    assert result['stats']['attached'] == 0


# ── 字面量回退（身份路径未命中时）──


def test_null_asset_type_orphan_attaches_by_literal_fallback(db):
    """孤儿 `asset_type` 为 NULL 时仍能按字面量挂回同 (family, ledger) 下的持仓。

    `symbol_identity` 在 `asset_type` 缺失时算不出 venue，身份键会落 `NO_VENUE:...`，
    与持仓的 `EXCHANGE:/OTC:` 身份键错位 → 身份路径未命中。回退用持仓自身 `asset_type`
    反算孤儿身份键并校验通过后挂回（真实库实测：大量 legacy 流水 asset_type 为 NULL）。
    """
    pos = _position(db, '001167', asset_type='fund')
    txn = _orphan(db, '001167', asset_type=None)

    result = _job(db).run()

    db.refresh(txn)
    assert txn.position_id == pos.id
    assert result['stats']['attached'] == 1
    assert result['stats']['no_position'] == 0


def test_dirty_prefix_with_null_asset_type_attaches_to_position_venue(db):
    """脏前缀 `SZ011341`（实际是 OTC 基金）配 `asset_type=NULL`：venue 只能由持仓侧定。

    身份路径因 `SZ` 前缀 + 缺 asset_type 算成 `NO_VENUE:SZ011341`，与持仓
    `OTC:011341` 错位；回退按去前缀字面量 `011341` 找到持仓，且 `symbol_identity(
    'SZ011341', 'fund') == 'OTC:011341'` 校验通过 → 挂回（不凭前缀瞎猜 venue）。
    """
    pos = _position(db, '011341', asset_type='fund')
    txn = _orphan(db, 'SZ011341', asset_type=None)

    result = _job(db).run()

    db.refresh(txn)
    assert txn.position_id == pos.id
    assert result['stats']['attached'] == 1


def test_literal_fallback_skips_ambiguous_venues(db):
    """同一去前缀字面量映射出两个不同 venue 的持仓（stock + fund）→ 歧义，跳过而非随机挂。

    `positions` 上有 `UNIQUE(ledger_id, symbol)` 字面量唯一约束，故两条持仓必须用**不同字面量**
    存储（`159915` vs `SZ159915`）；但它们剥前缀后都落到 `159915`，且各自 `asset_type` 都能让孤儿
    `symbol_identity('159915', pos.asset_type)` 复算出自己的 `symbol_norm`（stock→`EXCHANGE:SZ159915`、
    fund→`OTC:159915`）→ 校验都通过。身份路径未命中后走字面量回退，两候选都有效 → 视为歧义，
    不挂（与身份路径的歧义处理口径一致：宁可不挂，也不挂错）。
    """
    _position(db, '159915', asset_type='stock')  # 字面量 159915 → EXCHANGE:SZ159915
    _position(db, 'SZ159915', asset_type='fund')  # 字面量 SZ159915 → 剥前缀 159915 → OTC:159915
    txn = _orphan(db, '159915', asset_type=None)

    result = _job(db).run()

    db.refresh(txn)
    assert txn.position_id is None, '歧义时必须不挂'
    assert result['stats']['ambiguous'] == 1
    assert result['stats']['attached'] == 0


def test_literal_fallback_no_position_when_no_matching_holder(db):
    """回退路径也没有同字面量持仓 → 计入 no_position，绝不挂到无关持仓。"""
    _position(db, '159915', asset_type='stock')
    txn = _orphan(db, '999999', asset_type=None)  # 无任何持仓匹配

    result = _job(db).run()

    db.refresh(txn)
    assert txn.position_id is None
    assert result['stats']['no_position'] == 1
    assert result['stats']['attached'] == 0

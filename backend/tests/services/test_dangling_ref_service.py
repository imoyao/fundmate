# -*- coding: utf-8 -*-
"""#2866 后端：dangling_ref_service 单元测试（临时文件库，绝不连真库 invest.db）。

用仓库既有 ``db`` fixture（tests/conftest.py，临时文件库 + autouse clean_db），直接把
Session 传给纯业务函数；这与视图 ``with user_session() as db:`` 的「单事务」同构，
但全程不依赖 Flask / 不碰真库。

变异探针见 ``test_scan_distinguishes_dangling_normal_and_null`` 的注释。
"""

import json
from datetime import date, datetime, timedelta

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.reconciliation.models import AdjustmentLog
from app.domains.transactions.models import Transaction
from app.services import dangling_ref_service as svc

_FAMILY = 1
_OTHER_FAMILY = 2
_DANGLING_PID = 990001  # 不存在的持仓 id（position_id 无外键，可安全写入）
_BASE = datetime(2026, 1, 1, 9, 0, 0)  # naive datetime，与库里读回的 DateTime 同构


@pytest.fixture
def ledger(db):
    lg = Ledger(name='2866-测试账户', ledger_type='bank', family_id=_FAMILY)
    db.add(lg)
    db.flush()
    return lg


@pytest.fixture
def ledger2(db):
    lg = Ledger(name='2866-第二账户', ledger_type='bank', family_id=_FAMILY)
    db.add(lg)
    db.flush()
    return lg


def _mk_pos(db, ledger_id, symbol, shares, *, family_id=_FAMILY, ownership_status='active', name=None, asset_type=None):
    """按「份」建持仓（内部转最小单位）。name 传 '' 可造空名（display_name 回退链的用例）。

    cleared 行必须 quantity=0 —— positions 模型有 CheckConstraint
    ``ownership_status <> 'cleared' OR quantity = 0``，造非零 cleared 会 flush 失败。
    """
    qty = Money.shares_to_min_unit(0 if ownership_status == 'cleared' else shares)
    p = Position(
        family_id=family_id,
        ledger_id=ledger_id,
        symbol=symbol,
        name=symbol if name is None else name,
        market='CN_A',
        currency='CNY',
        quantity=qty,
        avg_price=Money.yuan_to_price_units(1.0),
        current_price=Money.yuan_to_price_units(1.0),
        ownership_status=ownership_status,
        asset_type=asset_type,
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
    txn_type='buy',
    shares=1.0,
    amount_cents=10000,
    created_at=None,
    trade_date=None,
    confirm_date=None,
    position_name=None,
    asset_type=None,
):
    """建一条流水。position_id 默认指向不存在的持仓（悬空）；传 None 造 NULL 孤儿。"""
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
        status='success',
        trade_date=trade_date,
        confirm_date=confirm_date,
        created_at=created_at if created_at is not None else _BASE,
        position_name=position_name,
    )
    db.add(t)
    db.flush()
    return t


# ── 检出 / 分组 / 净额 / 批次 / flags ──────────────────────────────────────


def test_scan_distinguishes_dangling_normal_and_null(db, ledger):
    """检出必须只挑出「position_id 指向已删除持仓」的流水，且按 family 过滤。

    四类数据同时存在：
    - 悬空：position_id = 不存在的 id → 应检出；
    - 正常：position_id = 现存持仓 id → 不应检出（NOT EXISTS 命中）；
    - NULL：position_id IS NULL（孤儿流水，非本卡范畴）→ 不应检出；
    - 跨 family 悬空：family_id=2 → 不应检出。

    **变异探针（手工跑，不在代码里写死实现）**：把 ``_dangling_condition`` 里
    「NOT EXISTS 相关子查询」整项去掉、只留 ``position_id IS NOT NULL + family``，
    再单跑本用例。`正常` 那条会被一并算作悬空：``total`` 由 1 变 2、``all_ids``
    混入正常流水 id，下面两条断言随之失败 —— 以此证明 NOT EXISTS（且必须是相关
    子查询、能在有/无持仓行间区分）是检出正确性的必要件，而非可选装饰。
    """
    live = _mk_pos(db, ledger.id, '000001', 1.0)
    dangling = _mk_txn(db, ledger.id, position_id=_DANGLING_PID, symbol='000001')
    _mk_txn(db, ledger.id, position_id=live.id, symbol='000001')  # 正常
    _mk_txn(db, ledger.id, position_id=None, symbol='000001')  # NULL 孤儿
    _mk_txn(db, ledger.id, position_id=_DANGLING_PID, symbol='000001', family_id=_OTHER_FAMILY)  # 跨 family

    data = svc.scan_dangling_refs(db, _FAMILY)
    assert data['total'] == 1
    all_ids = [t['id'] for g in data['groups'] for t in g['transactions']]
    assert all_ids == [dangling.id]


def test_scan_flags_cross_family_position_ref_as_dangling(db, ledger):
    """position_id 指向别家现存持仓 ⇒ 对本家庭仍是悬空，不许静默放过。

    多家庭隔离：只看 ``p.id`` 命中就判「正常」，会让本家庭的一条流水被别家的
    持仓行"认领"，扫描少报且 reattach 可能把数据挂到别家账上。
    **变异探针**：把 ``_dangling_condition`` 的 ``Position.family_id == family_id``
    去掉，本例必须从 total=1 变成 0 而失败。
    """
    foreign_pos = _mk_pos(db, ledger.id, '000001', 1.0, family_id=_OTHER_FAMILY)
    t = _mk_txn(db, ledger.id, position_id=foreign_pos.id, symbol='000001')

    data = svc.scan_dangling_refs(db, _FAMILY)
    assert data['total'] == 1
    assert data['groups'][0]['transactions'][0]['id'] == t.id
    # 别家视角里这条流水不属于自己，主查询 family 过滤仍生效
    assert svc.scan_dangling_refs(db, _OTHER_FAMILY)['total'] == 0


def test_groups_and_empty_symbol_isolated(db, ledger):
    """分组键 (ledger, symbol or '')：空 symbol 独立成组，不与有 symbol 的组混合。"""
    _mk_txn(db, ledger.id, symbol='A', created_at=_BASE)
    _mk_txn(db, ledger.id, symbol='A', created_at=_BASE + timedelta(seconds=10))
    _mk_txn(db, ledger.id, symbol='B', created_at=_BASE + timedelta(seconds=20))
    _mk_txn(db, ledger.id, symbol='', created_at=_BASE + timedelta(seconds=30))
    _mk_txn(db, ledger.id, symbol=None, created_at=_BASE + timedelta(seconds=40))

    data = svc.scan_dangling_refs(db, _FAMILY)
    assert data['group_count'] == 3
    by_key = {g['key']: g for g in data['groups']}
    assert set(by_key) == {f'{ledger.id}|A', f'{ledger.id}|B', f'{ledger.id}|'}
    assert by_key[f'{ledger.id}|A']['txn_count'] == 2
    assert by_key[f'{ledger.id}|B']['txn_count'] == 1
    # '' 与 None 都归一到同一个空 symbol 组
    assert by_key[f'{ledger.id}|']['txn_count'] == 2
    assert 'no_symbol' in by_key[f'{ledger.id}|']['flags']


def test_net_units_divided_by_10000(db, ledger):
    """净额 = Σ(买/存/拆) − Σ(卖/取)，单位「份」（最小单位 /10000）；amount(分) 不混用。"""
    _mk_txn(db, ledger.id, txn_type='buy', shares=1.0)
    _mk_txn(db, ledger.id, txn_type='deposit', shares=2.0)
    _mk_txn(db, ledger.id, txn_type='split', shares=0.5)
    _mk_txn(db, ledger.id, txn_type='sell', shares=0.3)
    _mk_txn(db, ledger.id, txn_type='withdraw', shares=0.2)
    # 非方向类型与 amount（分）都不得混进净额
    _mk_txn(db, ledger.id, txn_type='dividend', shares=99.0, amount_cents=123456)

    data = svc.scan_dangling_refs(db, _FAMILY)
    assert len(data['groups']) == 1
    g = data['groups'][0]
    assert g['net_units'] == pytest.approx(3.0)  # (1+2+0.5-0.3-0.2) = 3.0 份
    assert g['txn_count'] == 6
    assert g['dangling_position_ids'] == [_DANGLING_PID]
    # 对外统一换算：quantity 是「份」、amount 是「元」，前端直接显示不得再换一次
    buy = next(t for t in g['transactions'] if t['txn_type'] == 'buy')
    assert buy['quantity'] == pytest.approx(1.0)
    dividend = next(t for t in g['transactions'] if t['txn_type'] == 'dividend')
    assert dividend['amount'] == pytest.approx(1234.56)


def test_batch_clustering_600s(db, ledger):
    """按 created_at 排序，相邻间隔 > 600 秒切新批；label 取该批首条 YYYY-MM-DD HH:MM。"""
    # 0s / 100s 一批；800s（距上条 700>600）切新批；850s（距上条 50）留在第二批
    _mk_txn(db, ledger.id, symbol='A', created_at=_BASE)
    _mk_txn(db, ledger.id, symbol='A', created_at=_BASE + timedelta(seconds=100))
    _mk_txn(db, ledger.id, symbol='A', created_at=_BASE + timedelta(seconds=800))
    _mk_txn(db, ledger.id, symbol='A', created_at=_BASE + timedelta(seconds=850))

    data = svc.scan_dangling_refs(db, _FAMILY)
    assert data['batch_count'] == 2
    b1, b2 = data['batches']
    assert b1['id'] == 1 and b1['txn_count'] == 2 and b1['label'] == '2026-01-01 09:00'
    assert b2['id'] == 2 and b2['txn_count'] == 2 and b2['label'] == '2026-01-01 09:13'
    assert b1['ledger_ids'] == [ledger.id]
    assert b1['symbol_count'] == 1
    # 组取组内最早一条所属批次
    assert data['groups'][0]['batch_id'] == 1
    assert data['groups'][0]['batch_label'] == '2026-01-01 09:00'


def test_list_counts_and_flags(db, ledger):
    """全局计数 + 候选只列同标的 + fixable 由后端一处判据给出。"""
    live = _mk_pos(db, ledger.id, '000001', 1.0)
    _mk_pos(db, ledger.id, '000002', 0.0, ownership_status='cleared')  # 别的标的，不得进候选
    # symbol=000001 净额 3.0 份 vs live 1.0 份 → net_mismatch
    _mk_txn(db, ledger.id, symbol='000001', txn_type='buy', shares=3.0, trade_date=_BASE)
    # 空 symbol 且 trade_date 为空 → 计入全局 null_symbol / null_trade_date
    _mk_txn(db, ledger.id, symbol='', trade_date=None)

    data = svc.scan_dangling_refs(db, _FAMILY)
    assert data['total'] == 2
    assert data['null_symbol'] == 1
    assert data['null_trade_date'] == 1
    assert data['fixable_count'] == 1  # 只有 000001 那一组的 1 条可回补
    by_key = {g['key']: g for g in data['groups']}
    g = by_key[f'{ledger.id}|000001']
    assert g['live_position']['id'] == live.id
    assert g['live_position']['quantity'] == pytest.approx(1.0)  # 已换算成「份」
    # 候选只列同账本同标的：别的标的 cleared 行不该出现，否则会诱导挂错
    assert len(g['candidates']) == 1
    assert g['candidates'][0]['symbol'] == '000001'
    assert {'has_candidate', 'net_mismatch'} <= set(g['flags'])
    assert 'cleared_target' not in g['flags']
    assert g['fixable'] is True and g['block_reason'] is None

    blocked = by_key[f'{ledger.id}|']
    assert {'no_symbol', 'blocked'} <= set(blocked['flags'])
    assert blocked['fixable'] is False
    assert 'symbol' in blocked['block_reason']
    assert blocked['candidates'] == []


def test_group_display_name_prefers_live_then_txn_snapshot(db, ledger):
    """组级 display_name 取名链：live 名 → 候选名 → 组内流水快照 position_name，首个非空。

    「只有 candidate 而无 live」经 ``_group_candidates`` 的不变量（candidates[0] 就是
    live）不可单独构造，中间链由「live 名为空 → 回退流水快照」那条覆盖。
    """
    # live 存在 → 取 live.name
    _mk_pos(db, ledger.id, '000001', 1.0, name='平安银行')
    _mk_txn(db, ledger.id, symbol='000001')
    # 无任何同标的持仓（无 live 无候选）→ 回退组内流水快照 position_name
    _mk_txn(db, ledger.id, symbol='600000', position_name='浦发银行')
    # live / 候选 / 流水快照全空 → None
    _mk_txn(db, ledger.id, symbol='300750')
    # live 存在但名为空（候选[0] 即 live，名同为空）→ 继续回退到流水快照
    _mk_pos(db, ledger.id, '600519', 1.0, name='')
    _mk_txn(db, ledger.id, symbol='600519', position_name='贵州茅台')

    by_key = {g['key']: g for g in svc.scan_dangling_refs(db, _FAMILY)['groups']}
    assert by_key[f'{ledger.id}|000001']['display_name'] == '平安银行'
    assert by_key[f'{ledger.id}|600000']['display_name'] == '浦发银行'
    assert by_key[f'{ledger.id}|300750']['display_name'] is None
    assert by_key[f'{ledger.id}|600519']['display_name'] == '贵州茅台'
    # 组内流水明细与持仓摘要同步直出名，前端不必再拼
    assert by_key[f'{ledger.id}|600519']['transactions'][0]['position_name'] == '贵州茅台'
    assert by_key[f'{ledger.id}|000001']['live_position']['name'] == '平安银行'
    assert by_key[f'{ledger.id}|000001']['candidates'][0]['name'] == '平安银行'


def test_fixable_requires_same_symbol_live_position(db, ledger):
    """有 symbol 但同账本无同标的持仓行 ⇒ 不可回补，且给出可执行的下一步。"""
    _mk_pos(db, ledger.id, '000002', 1.0)
    _mk_txn(db, ledger.id, symbol='000001', txn_type='buy', shares=3.0)

    data = svc.scan_dangling_refs(db, _FAMILY)
    assert data['fixable_count'] == 0
    g = data['groups'][0]
    assert g['fixable'] is False and g['live_position'] is None
    assert g['candidates'] == []
    assert '重建持仓' in g['block_reason']


def test_cleared_target_flag_only_for_same_symbol(db, ledger):
    """cleared_target 只标「同标的现存行是 cleared」，不标同账本其它标的。"""
    _mk_pos(db, ledger.id, '000001', 0.0, ownership_status='cleared')
    _mk_pos(db, ledger.id, '000002', 0.0, ownership_status='cleared')
    _mk_txn(db, ledger.id, symbol='000001', txn_type='buy', shares=1.0)

    g = svc.scan_dangling_refs(db, _FAMILY)['groups'][0]
    assert 'cleared_target' in g['flags']
    assert [c['symbol'] for c in g['candidates']] == ['000001']


# ── preview 只读 ──────────────────────────────────────────────────────────


def test_preview_is_readonly(db, ledger):
    """preview 纯只读：不写库、不重算、数量全是预估 / 份。"""
    target = _mk_pos(db, ledger.id, '000001', 2.0)
    t1 = _mk_txn(
        db, ledger.id, symbol='000001', txn_type='buy', shares=1.0, trade_date=_BASE, confirm_date=_BASE.date()
    )
    t2 = _mk_txn(
        db, ledger.id, symbol='000001', txn_type='sell', shares=0.25, trade_date=_BASE, confirm_date=_BASE.date()
    )
    before_pids = {t1.id: t1.position_id, t2.id: t2.position_id}
    before_qty = target.quantity

    data = svc.preview_reattach(db, _FAMILY, [t1.id, t2.id], target.id)

    assert data['txn_count'] == 2
    assert data['target_position']['id'] == target.id
    assert data['quantity_before'] == pytest.approx(2.0)
    assert data['quantity_if_recomputed'] == pytest.approx(2.75)  # 2.0 + (1.0 - 0.25)
    assert data['delta'] == pytest.approx(0.75)
    assert data['safe'] is False  # 净额 0.75 与现存 2.0 差异 > 0.0001
    assert any('net_mismatch' in w for w in data['warnings'])
    assert any('预估' in w for w in data['warnings'])  # 口径限制如实给出
    # 纯只读：不写库、不重算份额
    assert db.query(Transaction).count() == 2
    assert db.query(AdjustmentLog).count() == 0
    for tid, old in before_pids.items():
        assert db.query(Transaction).filter_by(id=tid).one().position_id == old
    assert db.query(Position).filter_by(id=target.id).one().quantity == before_qty


# ── reattach 硬安全约束 ───────────────────────────────────────────────────


def test_reattach_default_no_recompute(db, ledger):
    """默认 recompute=False：只改 position_id、绝不重算份额；审计日志 before/after 落库。"""
    target = _mk_pos(db, ledger.id, '000001', 2.0)
    t1 = _mk_txn(db, ledger.id, symbol='000001', txn_type='buy', shares=1.0)
    t2 = _mk_txn(db, ledger.id, symbol='000001', txn_type='sell', shares=0.25)
    old_qty = target.quantity

    data = svc.reattach_transactions(db, _FAMILY, [t1.id, t2.id], target.id, reason='人工核对后挂回')

    assert data['updated'] == 2
    assert data['recompute'] is False
    assert data['quantity_after'] == data['quantity_before'] == pytest.approx(2.0)
    assert db.query(Transaction).filter_by(id=t1.id).one().position_id == target.id
    assert db.query(Transaction).filter_by(id=t2.id).one().position_id == target.id
    assert db.query(Position).filter_by(id=target.id).one().quantity == old_qty  # 份额一字不动
    log = db.query(AdjustmentLog).filter_by(action='dangling_ref_reattach').one()
    assert log.reason == '人工核对后挂回'
    before = json.loads(log.before_json)
    after = json.loads(log.after_json)
    assert {b['position_id'] for b in before} == {_DANGLING_PID}
    assert after['recompute'] is False
    assert {x['position_id'] for x in after['transactions']} == {target.id}
    assert data['log_id'] == log.id


def test_reattach_rejects_cross_family_and_fixed_id(db, ledger):
    """约束 2：跨 family / 已修好（position_id 指向现存持仓）的 id 整体 400、不写任何东西。"""
    target = _mk_pos(db, ledger.id, '000001', 1.0)
    fixed = _mk_txn(db, ledger.id, position_id=target.id, symbol='000001')
    foreign = _mk_txn(db, ledger.id, position_id=_DANGLING_PID, symbol='000001', family_id=_OTHER_FAMILY)

    for ids in ([fixed.id], [foreign.id]):
        with pytest.raises(ValueError):
            svc.reattach_transactions(db, _FAMILY, ids, target.id)
        assert db.query(AdjustmentLog).count() == 0
        assert db.query(Transaction).filter_by(id=fixed.id).one().position_id == target.id
        assert db.query(Transaction).filter_by(id=foreign.id).one().position_id == _DANGLING_PID


def test_reattach_rejects_cross_ledger_missing_target_and_null_ledger(db, ledger, ledger2):
    """约束 3：跨 ledger / 目标不存在 / txn.ledger_id 为 NULL 一律拒绝、不写任何东西。"""
    target = _mk_pos(db, ledger.id, '000001', 1.0)
    cross = _mk_txn(db, ledger2.id, position_id=_DANGLING_PID, symbol='000001')
    null_ledger = _mk_txn(db, None, position_id=_DANGLING_PID, symbol='000001')

    with pytest.raises(ValueError):
        svc.reattach_transactions(db, _FAMILY, [cross.id], target.id)  # 跨 ledger
    with pytest.raises(ValueError):
        svc.reattach_transactions(db, _FAMILY, [cross.id], 999999)  # 目标不存在
    with pytest.raises(ValueError):
        svc.reattach_transactions(db, _FAMILY, [null_ledger.id], target.id)  # ledger_id 为 NULL
    assert db.query(AdjustmentLog).count() == 0
    assert db.query(Transaction).filter_by(id=cross.id).one().position_id == _DANGLING_PID
    assert db.query(Transaction).filter_by(id=null_ledger.id).one().position_id == _DANGLING_PID


def test_reattach_rejects_missing_or_mismatched_symbol(db, ledger):
    """约束 3b：缺 symbol / symbol 与目标持仓不一致一律拒绝，不许把流水挂到别的标的。

    真库最大一组是 293 条空 symbol 卖出流水，同账本却有 20 个候选持仓；
    只校验 ledger 时用户随手选一个就会制造错账。这是「挂错比不改更坏」的回归网。
    """
    target = _mk_pos(db, ledger.id, '000001', 1.0)
    no_symbol = _mk_txn(db, ledger.id, symbol='', txn_type='sell', shares=1.0)
    mismatch = _mk_txn(db, ledger.id, symbol='000002', txn_type='buy', shares=1.0)

    for t in (no_symbol, mismatch):
        with pytest.raises(ValueError) as ei:
            svc.reattach_transactions(db, _FAMILY, [t.id], target.id)
        assert 'symbol' in str(ei.value)
        assert db.query(Transaction).filter_by(id=t.id).one().position_id == _DANGLING_PID
    assert db.query(AdjustmentLog).count() == 0


@pytest.mark.parametrize('ids', [None, [], [1, 2] * 300, ['x'], [True], [1.5]])
def test_reattach_validates_ids(db, ledger, ids):
    """约束 1：非空 int 列表、≤500、bool/非 int 拒绝。"""
    target = _mk_pos(db, ledger.id, '000001', 1.0)
    with pytest.raises(ValueError):
        svc.reattach_transactions(db, _FAMILY, ids, target.id)
    assert db.query(AdjustmentLog).count() == 0


def test_reattach_validates_recompute_flag(db, ledger):
    """recompute 必须是严格 bool：'true' / 1 / 'false' / [] 都不得被当成 True。"""
    target = _mk_pos(db, ledger.id, '000001', 1.0)
    t = _mk_txn(db, ledger.id, position_id=_DANGLING_PID, symbol='000001')
    for bad in ('true', 1, 'false', []):
        with pytest.raises(ValueError):
            svc.reattach_transactions(db, _FAMILY, [t.id], target.id, recompute=bad)
    assert db.query(AdjustmentLog).count() == 0


def test_recompute_true_is_rejected(db, ledger):
    """自动重算已禁用：即使 safe=True，recompute=true 也一律 400、不写任何东西。

    真重算会改份额且不可逆（含清仓复活 / 删行副作用），不属于「安全的二次回补」。
    变异探针：把 service 里 `if recompute: raise ValueError(...)` 删掉，本例必须失败。
    """
    target = _mk_pos(db, ledger.id, '000001', 1.0)
    t = _mk_txn(db, ledger.id, symbol='000001', txn_type='buy', shares=1.0)  # 净额 1.0 == 现存 1.0
    with pytest.raises(ValueError) as ei:
        svc.reattach_transactions(db, _FAMILY, [t.id], target.id, recompute=True)
    assert '禁用' in str(ei.value)
    assert db.query(AdjustmentLog).count() == 0
    assert db.query(Transaction).filter_by(id=t.id).one().position_id == _DANGLING_PID


def test_reattach_allowed_when_data_inconsistent(db, ledger):
    """safe=false（净额 ≠ 现存份额）仍允许回补：挂回只改指针，份额一字不动。

    真库 122 组里 100 组净额≠0、295 条缺 symbol。若把 safe 当提交闸门，
    用户几乎一条都修不了 —— 这是 #2866「可以修复」的回归网，不许退化。
    """
    target = _mk_pos(db, ledger.id, '000001', 1.0)
    t = _mk_txn(db, ledger.id, symbol='000001', txn_type='buy', shares=3.0)  # 净额 3.0 vs 现存 1.0
    preview = svc.preview_reattach(db, _FAMILY, [t.id], target.id)
    assert preview['safe'] is False

    data = svc.reattach_transactions(db, _FAMILY, [t.id], target.id)
    assert data['updated'] == 1
    assert db.query(Transaction).filter_by(id=t.id).one().position_id == target.id
    assert db.query(Position).filter_by(id=target.id).one().quantity == Money.shares_to_min_unit(1.0)


def test_reattach_reports_share_mismatch_after_attach(db, ledger):
    """#3127 形态：买入腿早已挂在该持仓上、卖腿挂回后净额归零，份额却不动 ⇒ 必须当场报差异。

    契约仍是「不自动重算」（``quantity_after == quantity_before``），但「挂回后份额与流水
    不自洽」这件事要可见——真库 95 条幽灵持仓正是因为一路无人回答才留了下来。
    """
    target = _mk_pos(db, ledger.id, 'SZ128101', 2.0)
    _mk_txn(db, ledger.id, position_id=target.id, symbol='SZ128101', txn_type='buy', shares=2.0)
    sell = _mk_txn(db, ledger.id, symbol='SZ128101', txn_type='sell', shares=2.0)

    data = svc.reattach_transactions(db, _FAMILY, [sell.id], target.id)

    assert data['quantity_after'] == pytest.approx(2.0)  # 契约：份额一字不动
    check = data['share_check']
    assert check['quantity_now'] == pytest.approx(2.0)
    assert check['quantity_if_recomputed'] == pytest.approx(0.0)
    assert check['diff'] == pytest.approx(-2.0)
    assert check['recompute_suggested'] is True
    # 净额 0 ⇒ 提示必须指向「核对流水 / 按账单填 0」，不再建议按流水重算（2026-11-16 定调）
    assert '改成账单份额' in (check['hint'] or '')
    assert '不能据此清仓' in (check['hint'] or '')
    assert db.query(Position).filter_by(id=target.id).one().quantity == Money.shares_to_min_unit(2.0)


def test_reattach_share_check_clean_when_flows_match(db, ledger):
    """挂回后份额与流水自洽 ⇒ 不提示（否则每次都弹，真提示会被忽略）。"""
    target = _mk_pos(db, ledger.id, '000001', 2.0)
    _mk_txn(db, ledger.id, position_id=target.id, symbol='000001', txn_type='buy', shares=3.0)
    sell = _mk_txn(db, ledger.id, symbol='000001', txn_type='sell', shares=1.0)

    data = svc.reattach_transactions(db, _FAMILY, [sell.id], target.id)

    check = data['share_check']
    assert check['quantity_if_recomputed'] == pytest.approx(2.0)
    assert check['recompute_suggested'] is False
    assert check['hint'] is None


def test_reattach_share_check_respects_anchor(db, ledger):
    """有锚点的持仓：锚点前的流水本来就不计入份额，不能算成差异（否则每笔都假报）。

    这条钉住「必须复用 ``compute_anchored_state``」：换成自己按流水求和会得到 8 份，
    与真实 5 份差 3，把一笔合法挂回报成「份额错了」。
    """
    target = _mk_pos(db, ledger.id, '000001', 5.0)
    target.snapshot_quantity = Money.shares_to_min_unit(5.0)
    target.snapshot_avg_price = Money.yuan_to_price_units(1.0)
    target.snapshot_date = date(2026, 6, 30)
    db.flush()
    older = _mk_txn(
        db,
        ledger.id,
        symbol='000001',
        txn_type='buy',
        shares=3.0,
        trade_date=datetime(2025, 12, 1, 9, 0, 0),
        confirm_date=date(2025, 12, 1),  # confirm_date 是 Date 列，与 snapshot_date 同型
    )

    data = svc.reattach_transactions(db, _FAMILY, [older.id], target.id)

    check = data['share_check']
    assert check['quantity_if_recomputed'] == pytest.approx(5.0)
    assert check['recompute_suggested'] is False


# ── undo ──────────────────────────────────────────────────────────────────


def test_undo_restores_and_is_idempotent(db, ledger):
    """undo 把 position_id 恢复成 before 值；重复撤销 restored=0、数据不变（幂等）。"""
    target = _mk_pos(db, ledger.id, '000001', 1.0)
    t1 = _mk_txn(db, ledger.id, position_id=_DANGLING_PID, symbol='000001', txn_type='buy', shares=1.0)
    t2 = _mk_txn(db, ledger.id, position_id=_DANGLING_PID, symbol='000001', txn_type='sell', shares=0.25)
    ret = svc.reattach_transactions(db, _FAMILY, [t1.id, t2.id], target.id)
    log_id = ret['log_id']

    first = svc.undo_reattach(db, _FAMILY, log_id)
    assert first == {'restored': 2, 'log_id': log_id}
    assert db.query(Transaction).filter_by(id=t1.id).one().position_id == _DANGLING_PID
    assert db.query(Transaction).filter_by(id=t2.id).one().position_id == _DANGLING_PID
    assert db.query(AdjustmentLog).filter_by(action='dangling_ref_undo').count() == 1

    # 幂等：重复撤销 restored=0，数据不变（按契约仍追加一条留痕）
    second = svc.undo_reattach(db, _FAMILY, log_id)
    assert second['restored'] == 0
    assert db.query(Transaction).filter_by(id=t1.id).one().position_id == _DANGLING_PID
    assert db.query(AdjustmentLog).filter_by(action='dangling_ref_undo').count() == 2


def test_undo_skips_txn_whose_position_changed(db, ledger):
    """约束 6：仅当 txn 当前 position_id 仍等于 after 值才恢复，否则跳过且不覆盖人工改动。"""
    target = _mk_pos(db, ledger.id, '000001', 1.0)
    other = _mk_pos(db, ledger.id, '000003', 1.0)
    t1 = _mk_txn(db, ledger.id, position_id=_DANGLING_PID, symbol='000001', txn_type='buy', shares=1.0)
    t2 = _mk_txn(db, ledger.id, position_id=_DANGLING_PID, symbol='000001', txn_type='buy', shares=1.0)
    ret = svc.reattach_transactions(db, _FAMILY, [t1.id, t2.id], target.id)
    # 模拟期间其它写入：把 t2 人工挂到别的持仓
    db.query(Transaction).filter_by(id=t2.id).one().position_id = other.id
    db.flush()

    result = svc.undo_reattach(db, _FAMILY, ret['log_id'])
    assert result['restored'] == 1
    assert db.query(Transaction).filter_by(id=t1.id).one().position_id == _DANGLING_PID
    assert db.query(Transaction).filter_by(id=t2.id).one().position_id == other.id  # 未被改动


def test_undo_rejects_legacy_recomputed_batch(db, ledger):
    """防御：历史 recompute=true 日志份额不可逆，拒绝自动撤销、提示人工处理、不留 undo 日志。

    本版本 reattach 不会再产生这类日志（recompute=true 一律 400），但库里若留有旧日志，
    undo 必须拒绝，绝不能只恢复指针却把已被重算过的份额留在原地。
    """
    target = _mk_pos(db, ledger.id, '000001', 1.0)
    t = _mk_txn(db, ledger.id, position_id=target.id, symbol='000001', txn_type='buy', shares=1.0)
    legacy = AdjustmentLog(
        family_id=_FAMILY,
        action='dangling_ref_reattach',
        before_json=json.dumps([{'id': t.id, 'position_id': _DANGLING_PID}]),
        after_json=json.dumps(
            {
                'recompute': True,
                'target_position_id': target.id,
                'transactions': [{'id': t.id, 'position_id': target.id}],
            }
        ),
    )
    db.add(legacy)
    db.flush()

    with pytest.raises(ValueError) as ei:
        svc.undo_reattach(db, _FAMILY, legacy.id)
    assert '人工' in str(ei.value)
    # 拒绝时不改动 txn、不写 undo 日志
    assert db.query(Transaction).filter_by(id=t.id).one().position_id == target.id
    assert db.query(AdjustmentLog).filter_by(action='dangling_ref_undo').count() == 0


# ── 视图端点冒烟：验证 4 个 URL 的编排（信封 / 400 / 单事务写）─────────────────
# client 走独立请求会话（user_session），故测试数据需先 db.commit() 才可见 ——
# 与仓库既有 API 测试（tests/services/test_pnl_attribution_api.py）同一套路。


def test_endpoint_list_and_preview(client, db, ledger):
    """GET 列表 / preview 返回 {'data':..., 'message':'ok'}，preview 不写库。"""
    target = _mk_pos(db, ledger.id, '000001', 2.0)
    t1 = _mk_txn(db, ledger.id, symbol='000001', txn_type='buy', shares=1.0)
    t1_id, target_id = t1.id, target.id
    db.commit()

    resp = client.get('/api/reconciliation/dangling-refs/')
    assert resp.status_code == 200
    listed = resp.get_json()
    assert listed['message'] == 'ok'
    assert listed['data']['total'] == 1

    resp = client.get(
        f'/api/reconciliation/dangling-refs/preview/?transaction_ids={t1_id}&target_position_id={target_id}'
    )
    assert resp.status_code == 200
    preview = resp.get_json()['data']
    assert preview['txn_count'] == 1
    assert preview['quantity_before'] == pytest.approx(2.0)
    # preview 只读：无审计日志、position_id 未变
    assert db.query(AdjustmentLog).count() == 0
    assert db.query(Transaction).filter_by(id=t1_id).one().position_id == _DANGLING_PID


def test_endpoint_reattach_and_undo(client, db, ledger):
    """POST reattach / undo 在单个请求事务里落库，信封结构符合契约。"""
    target = _mk_pos(db, ledger.id, '000001', 1.0)
    t1 = _mk_txn(db, ledger.id, symbol='000001', txn_type='buy', shares=1.0)
    t1_id, target_id = t1.id, target.id
    db.commit()

    resp = client.post(
        '/api/reconciliation/dangling-refs/reattach/',
        json={'transaction_ids': [t1_id], 'target_position_id': target_id, 'reason': '接口挂回'},
    )
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['updated'] == 1
    assert data['recompute'] is False
    log_id = data['log_id']

    resp = client.post('/api/reconciliation/dangling-refs/undo/', json={'log_id': log_id})
    assert resp.status_code == 200
    assert resp.get_json()['data'] == {'restored': 1, 'log_id': log_id}


def test_endpoint_bad_params_return_400(client):
    """参数错误一律 abort(400)：契约的 400 口径在 HTTP 层成立。"""
    assert (
        client.get('/api/reconciliation/dangling-refs/preview/?transaction_ids=1,abc&target_position_id=1').status_code
        == 400
    )
    assert client.get('/api/reconciliation/dangling-refs/preview/?transaction_ids=1').status_code == 400  # 缺 target
    assert (
        client.post(
            '/api/reconciliation/dangling-refs/reattach/', json={'transaction_ids': [], 'target_position_id': 1}
        ).status_code
        == 400
    )
    assert client.post('/api/reconciliation/dangling-refs/undo/', json={'log_id': 999999}).status_code == 400


# ── 标的分组身份（2026-11-15 真库事故：293 条 114 个标的被一次补全写成同一代码） ──


def test_scan_splits_blank_symbol_groups_by_product_name(db, ledger):
    """缺标的代码的流水按标的名拆组，不许把整本账的缺码流水并成一组。

    真库 2026-11-15：293 条空 symbol 流水（114 个标的）并成一组，组名取首个
    ``position_name`` 显示成「优彩转债」，一次「补全信息」就把 114 个标的刷成
    同一个代码。拆组后每组只有一个标的名，补全才有意义。

    **变异探针**：把分组键里的 ``name_key`` 去掉（退回 ``(ledger, symbol)``），
    本用例 groups 由 2 变 1、display_name 只剩一个 —— 断言随之失败。
    """
    _mk_txn(db, ledger.id, symbol=None, position_name='优彩转债')
    _mk_txn(db, ledger.id, symbol=None, position_name='精达转债')

    groups = svc.scan_dangling_refs(db, _FAMILY)['groups']

    assert len(groups) == 2
    assert {g['display_name'] for g in groups} == {'优彩转债', '精达转债'}
    # key 仍是 ledger|symbol（核对差异的覆盖判定按它比对），group_id 才唯一
    assert {g['key'] for g in groups} == {f'{ledger.id}|'}
    assert len({g['group_id'] for g in groups}) == 2


def test_scan_blocks_group_mixing_multiple_products(db, ledger):
    """symbol 相同但标的名分属不同标的 ⇒ 整组不可回补/重建，并点出「等 N 个标的」。

    293 条流水被补成 127078 后，symbol 一致而标的并不一致；只看 symbol 会判
    「可回补」，一键就把 114 个标的挂到同一行。

    **变异探针**：去掉 ``_group_block_reason`` 的 identity_count 分支，本用例
    ``fixable`` 由 False 变 True、flags 丢 ``mixed_identity`` —— 断言失败。
    """
    a = _mk_pos(db, ledger.id, 'SZ127078', 1.0)
    b = _mk_pos(db, ledger.id, 'SH110074', 1.0)
    # 正常流水只用来给「标的名 → symbol」建索引（悬空流水自身不参与建索引）
    _mk_txn(db, ledger.id, position_id=a.id, symbol='SZ127078', position_name='优彩转债')
    _mk_txn(db, ledger.id, position_id=b.id, symbol='SH110074', position_name='精达转债')
    _mk_txn(db, ledger.id, symbol='127078', position_name='优彩转债')
    _mk_txn(db, ledger.id, symbol='127078', position_name='精达转债')

    groups = svc.scan_dangling_refs(db, _FAMILY)['groups']

    assert len(groups) == 1
    group = groups[0]
    assert group['identity_count'] == 2
    assert group['fixable'] is False
    assert 'mixed_identity' in group['flags']
    assert '2 个不同标的' in group['block_reason']
    assert group['display_name'].endswith('等 2 个标的')


def test_reattach_rejects_batch_mixing_multiple_products(db, ledger):
    """回补写入前必须再过一道标的身份：symbol 全一致也不算同一批。

    只校验 symbol 的话，293 条（114 个标的、全被写成 127078）会被整体挂到
    优彩转债那一行，且每次挂回都会写审计日志、看起来"操作成功"。
    """
    a = _mk_pos(db, ledger.id, 'SZ127078', 1.0)
    b = _mk_pos(db, ledger.id, 'SH110074', 1.0)
    _mk_txn(db, ledger.id, position_id=a.id, symbol='SZ127078', position_name='优彩转债')
    _mk_txn(db, ledger.id, position_id=b.id, symbol='SH110074', position_name='精达转债')
    t1 = _mk_txn(db, ledger.id, symbol='127078', position_name='优彩转债')
    t2 = _mk_txn(db, ledger.id, symbol='127078', position_name='精达转债')
    target = _mk_pos(db, ledger.id, '127078', 1.0)

    with pytest.raises(ValueError, match='不同标的'):
        svc.reattach_transactions(db, _FAMILY, [t1.id, t2.id], target.id)
    # 拒绝分支不留痕：两条流水的归属一字未动
    assert all(t.position_id == _DANGLING_PID for t in (t1, t2))


# ── 标的身份：代码写法归一（裸码 ⇄ 带前缀）+ 场所相容 ──────────────────────


def test_reattach_accepts_bare_code_against_prefixed_position(db, ledger):
    """`127078` 与 `SZ127078` 是同一只标的：挂回必须放行。

    真库 2026-08-29 的券商交割单导入把 symbol 写成裸 6 位码，持仓行是 `SZ` 前缀。
    按字面量比较时，回补候选 0 条、手动指定目标又被同一处字面量判据拒绝，而重建侧
    按六位码展开查到既有持仓、回一句「请用回补关联」—— 整张卡两边互指、无路可走。
    """
    target = _mk_pos(db, ledger.id, 'SZ127078', 1.0, asset_type='bond')
    t = _mk_txn(db, ledger.id, symbol='127078', asset_type='bond', txn_type='sell', shares=1.0)

    out = svc.reattach_transactions(db, _FAMILY, [t.id], target.id)

    assert out['updated'] == 1
    assert db.query(Transaction).filter_by(id=t.id).one().position_id == target.id


def test_reattach_rejects_same_code_across_venues(db, ledger):
    """裸码撞车不能只靠归一码放行：`000001` 场外基金 ≠ `SZ000001` 平安银行。

    这是「写法归一」必须带场所约束的原因 —— 只比归一码会把场内股票流水挂到场外基金行上，
    比原来的字面量比较更糟（错账且看起来"通过校验"）。
    """
    target = _mk_pos(db, ledger.id, 'SZ000001', 1.0, asset_type='stock')
    t = _mk_txn(db, ledger.id, symbol='000001', asset_type='fund', txn_type='buy', shares=1.0)

    with pytest.raises(ValueError, match='不是同一标的'):
        svc.reattach_transactions(db, _FAMILY, [t.id], target.id)
    assert db.query(Transaction).filter_by(id=t.id).one().position_id == _DANGLING_PID
    assert db.query(AdjustmentLog).count() == 0


def test_scan_lists_candidates_for_equivalent_symbol_forms(db, ledger):
    """分组候选也要按同一标的匹配：否则「有候选」这件事永远显示为没有。"""
    pos = _mk_pos(db, ledger.id, 'SZ127078', 1.0, name='优彩转债', asset_type='bond')
    _mk_txn(db, ledger.id, symbol='127078', asset_type='bond', txn_type='sell', shares=1.0, position_name='优彩转债')

    group = svc.scan_dangling_refs(db, _FAMILY)['groups'][0]

    assert [c['id'] for c in group['candidates']] == [pos.id]
    assert group['fixable'] is True
    assert group['block_reason'] is None


def test_preview_does_not_warn_symbol_mismatch_for_equivalent_forms(db, ledger):
    """挂回预览的 safe/warnings 与写入判据同源：等价写法不该被报成「symbol 不一致」。"""
    target = _mk_pos(db, ledger.id, 'SZ127078', 1.0, asset_type='bond')
    t = _mk_txn(db, ledger.id, symbol='127078', asset_type='bond', txn_type='sell', shares=1.0)

    data = svc.preview_reattach(db, _FAMILY, [t.id], target.id)

    assert not [w for w in data['warnings'] if 'symbol' in w]


def test_reattach_allows_ambiguous_name_resolved_by_symbol(db, ledger):
    """一码多名（旅游ETF → SH562510 / SZ159766）时，显式指定的代码就是消歧结果，必须放行。

    否则这类组永远补不了：组内标的数按名字反查算成 2，连「一条流水」也被判成混标的，
    界面上没有任何按钮能走通 —— 与本次要除掉的死锁是同一类。
    """
    a = _mk_pos(db, ledger.id, 'SH562510', 180.0, name='旅游ETF', asset_type='etf')
    _mk_pos(db, ledger.id, 'SZ159766', 97.0, name='旅游ETF', asset_type='etf')
    t1 = _mk_txn(db, ledger.id, symbol='SH562510', position_name='旅游ETF', asset_type='etf', txn_type='sell')
    t2 = _mk_txn(db, ledger.id, symbol='SH562510', position_name='旅游ETF', asset_type='etf', txn_type='sell')

    out = svc.reattach_transactions(db, _FAMILY, [t1.id, t2.id], a.id)

    assert out['updated'] == 2
    assert all(db.query(Transaction).filter_by(id=t.id).one().position_id == a.id for t in (t1, t2))


def test_reattach_still_rejects_batch_whose_names_do_not_cover_symbol(db, ledger):
    """反向对照：名字里有一个不把该代码列为候选，就不是「一码多名」，仍按混标的拒绝。

    这条守的是真库那 293 条（114 个名字被写成同一个 `127078`）：只要有一个名字反查不到
    这个代码，整批就不能一起挂。
    """
    a = _mk_pos(db, ledger.id, 'SH562510', 180.0, name='旅游ETF', asset_type='etf')
    _mk_pos(db, ledger.id, 'SH600000', 1.0, name='浦发银行', asset_type='stock')
    t1 = _mk_txn(db, ledger.id, symbol='SH562510', position_name='旅游ETF', asset_type='etf')
    t2 = _mk_txn(db, ledger.id, symbol='SH562510', position_name='浦发银行', asset_type='stock')

    with pytest.raises(ValueError, match='不同标的'):
        svc.reattach_transactions(db, _FAMILY, [t1.id, t2.id], a.id)
    assert all(t.position_id == _DANGLING_PID for t in (t1, t2))

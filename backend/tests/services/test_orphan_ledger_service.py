# -*- coding: utf-8 -*-
"""#2875 后端：``orphan_ledger_service`` 单元测试（临时文件库，绝不连真库 invest.db）。

用仓库既有 ``db`` fixture（tests/conftest.py，临时文件库 + autouse clean_db），直接把
Session 传给纯业务函数；与视图 ``with user_session() as db:`` 的「单事务」同构，
全程不依赖 Flask / 不碰真库。

钉住三件最容易静默失效的事：

1. **检出条件**：``ledger_id IS NULL AND position_id IS NULL AND family_id`` 三个条件
   缺一不可。变异探针写在 ``test_scan_only_picks_both_null_and_same_family`` 里：
   去掉任一 IS NULL 条件，都会把「已有账本」或「挂了持仓」的行算进来。
2. **归属口径与 CLI 一致**：app 层不 import scripts（分层守卫），故按语义复刻；
   ``test_resolve_ledger_matches_cli`` 用同一批账本行同时喂两个实现逐例比对，
   任一例漂移即失败（含空名 / 去空白 / 无匹配 / 歧义 / 别家同名 / 大小写）。
3. **写入范围**：``backfill_orphan_ledgers`` 只准改 ``ledger_id`` 一列，且任一校验
   失败必须「整体拒绝、零写入」；``undo_backfill`` 只恢复当前值仍等于 after 的行。

单位口径：``amount`` 库内为「分」，序列化边界 /100 成「元」；``quantity`` 为
1/10000 最小单位、**不出现在任何响应里**（本接口一个字节都不碰它）。
"""

import importlib.util
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.reconciliation.models import AdjustmentLog
from app.domains.transactions.models import Transaction
from app.services import orphan_ledger_service as svc

_FAMILY = 1
_OTHER_FAMILY = 2
_ACCOUNT = '同花顺（银河证券）'
_BASE = datetime(2026, 1, 1, 9, 0, 0)  # naive datetime，与库里读回的 DateTime 同构
_CLI_PATH = Path(__file__).resolve().parents[2] / 'scripts' / 'fix_orphan_ledger_null.py'


@pytest.fixture
def ledger(db):
    lg = Ledger(name=_ACCOUNT, ledger_type='bank', family_id=_FAMILY)
    db.add(lg)
    db.flush()
    return lg


def _mk_ledger(db, name, family_id=_FAMILY):
    lg = Ledger(name=name, ledger_type='bank', family_id=family_id)
    db.add(lg)
    db.flush()
    return lg


def _mk_txn(
    db,
    *,
    ledger_id=None,
    position_id=None,
    family_id=_FAMILY,
    account_name=_ACCOUNT,
    symbol='',
    txn_type='dividend_tax',
    amount_cents=1234,
    created_at=_BASE,
    trade_date=None,
    confirm_date=None,
    position_name=None,
):
    """建一条流水：默认两个归属列都为 NULL（#2875 的检出对象）。

    ``position_id`` 无外键，传任意整数即可造「已挂持仓」的反例；``created_at``
    默认给 _BASE，传 None 造无时间行（批次聚簇的降级分支）。
    """
    t = Transaction(
        family_id=family_id,
        ledger_id=ledger_id,
        position_id=position_id,
        account_name=account_name,
        symbol=symbol,
        txn_type=txn_type,
        quantity=Money.shares_to_min_unit(1.0),
        price=Money.yuan_to_price_units(1.0),
        amount=amount_cents,
        status='success',
        trade_date=trade_date,
        confirm_date=confirm_date,
        created_at=created_at,
        position_name=position_name,
    )
    db.add(t)
    db.flush()
    return t


def _load_cli():
    """按路径加载 CLI 脚本（它在 backend/scripts/，不是可 import 的包）。"""
    spec = importlib.util.spec_from_file_location('fix_orphan_ledger_null', _CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── 检出 / 归属 / 分组 / 批次 ─────────────────────────────────────────────


def test_scan_only_picks_both_null_and_same_family(db, ledger):
    """检出必须只挑「两个归属列都为 NULL」且属于本家庭的流水。

    四类数据同时存在：孤儿（NULL+NULL）应检出；已有账本、已挂持仓、跨 family
    均不检出。

    **变异探针（手工跑，不在代码里写死实现）**：把 ``_orphan_condition`` 里的
    ``Transaction.ledger_id.is_(None)`` 去掉 ⇒ 「已有账本」那条被算进来，``total``
    由 1 变 2；去掉 ``Transaction.position_id.is_(None)`` ⇒ 「已挂持仓」那条被算进来，
    同样变 2；去掉 ``family_id`` ⇒ 跨 family 那条被算进来。三种变异都必须让本用例
    失败，证明三个条件都是必要件而非装饰。
    """
    orphan = _mk_txn(db)
    _mk_txn(db, ledger_id=ledger.id)
    _mk_txn(db, position_id=990001)
    _mk_txn(db, family_id=_OTHER_FAMILY)

    data = svc.scan_orphan_ledgers(db, _FAMILY)
    assert data['total'] == 1
    ids = [t['id'] for g in data['groups'] for t in g['transactions']]
    assert ids == [orphan.id]
    # 别家视角只看到自己那条（全库两条孤儿，family 过滤生效）
    assert svc.scan_orphan_ledgers(db, _OTHER_FAMILY)['total'] == 1


def test_scan_is_readonly_and_converts_amount(db, ledger):
    """GET 纯只读：不新增 / 不 UPDATE 任何行，不写审计日志；amount 分→元。"""
    t = _mk_txn(db, amount_cents=123456, trade_date=_BASE, confirm_date=_BASE.date())
    before = (t.ledger_id, t.position_id, t.quantity, t.amount, t.symbol)

    data = svc.scan_orphan_ledgers(db, _FAMILY)

    assert db.query(Transaction).count() == 1
    assert db.query(AdjustmentLog).count() == 0
    assert (t.ledger_id, t.position_id, t.quantity, t.amount, t.symbol) == before
    txn = data['groups'][0]['transactions'][0]
    assert float(txn['amount']) == pytest.approx(1234.56)
    assert txn['trade_date'] == _BASE.isoformat()
    assert txn['confirm_date'] == _BASE.date().isoformat()
    # 份额与任何持仓列都不返回（本接口不碰它们）
    assert 'quantity' not in txn
    assert 'position_id' not in txn


def test_scan_empty(db, ledger):
    """无孤儿时结构与计数全为 0，避免前端拿 null 做算术。"""
    assert svc.scan_orphan_ledgers(db, _FAMILY) == {
        'total': 0,
        'fixable_count': 0,
        'blocked_count': 0,
        'batch_count': 0,
        'groups': [],
        'batches': [],
    }


def test_resolve_ledger_matches_cli(db, ledger):
    """归属规则与 CLI ``fix_orphan_ledger_null.py::resolve_ledger`` 逐例一致。

    app 层不 import scripts（分层守卫），这里用同一批账本行同时喂两份实现比对：
    普通命中 / 前后空白 / 空串 / None / 纯空白 / 无匹配 / 歧义（同 family 两条同名）/
    别家同名 / 大小写不同。任一例漂移即失败——这是「两份实现不许各自演化」的网。
    """
    ambiguous = '歧义账户'
    _mk_ledger(db, ambiguous)
    _mk_ledger(db, ambiguous)
    _mk_ledger(db, _ACCOUNT, family_id=_OTHER_FAMILY)  # 别家同名，不参与本 family 匹配
    other = _mk_ledger(db, 'Broker A')  # 英文账户：大小写不同必须不命中（中文名无大小写，测不出来）

    cli = _load_cli()
    conn = sqlite3.connect(':memory:')
    try:
        conn.execute('CREATE TABLE ledgers (id INTEGER PRIMARY KEY, family_id INTEGER, name TEXT)')
        for lid, fid, name in db.query(Ledger.id, Ledger.family_id, Ledger.name).all():
            conn.execute('INSERT INTO ledgers VALUES (?, ?, ?)', (lid, fid, name))
        conn.commit()

        cases = [
            (_FAMILY, _ACCOUNT),
            (_FAMILY, f'  {_ACCOUNT}  '),
            (_FAMILY, ''),
            (_FAMILY, None),
            (_FAMILY, '   '),
            (_FAMILY, '不存在的账户'),
            (_FAMILY, ambiguous),
            (_FAMILY, other.name),
            (_FAMILY, other.name.lower()),  # 精确同名、区分大小写：不命中
            (_OTHER_FAMILY, _ACCOUNT),
            (None, _ACCOUNT),
        ]
        for family_id, account_name in cases:
            got = svc.resolve_ledger(db, family_id, account_name)
            expected = cli.resolve_ledger(conn, family_id, account_name)
            assert got == expected, f'口径漂移：family={family_id!r} name={account_name!r}'
    finally:
        conn.close()

    # 顺带钉住成功 / 歧义两条的具体形态，防止两份实现一起被改成「模糊匹配」
    assert svc.resolve_ledger(db, _FAMILY, _ACCOUNT) == (ledger.id, '')
    assert svc.resolve_ledger(db, _FAMILY, ambiguous)[0] is None
    assert '歧义' in svc.resolve_ledger(db, _FAMILY, ambiguous)[1]


def test_scan_groups_fixable_and_blocked(db, ledger):
    """可回填按 ledger 分组（key=ledger:{id}）；无法归属的全部进唯一 blocked 组。"""
    ok1 = _mk_txn(db, created_at=_BASE)
    ok2 = _mk_txn(db, created_at=_BASE + timedelta(seconds=10))
    no_match = _mk_txn(db, account_name='查无此账本')
    no_name = _mk_txn(db, account_name='  ')

    data = svc.scan_orphan_ledgers(db, _FAMILY)
    assert data['total'] == 4
    assert data['fixable_count'] == 2
    assert data['blocked_count'] == 2
    by_key = {g['key']: g for g in data['groups']}
    assert set(by_key) == {f'ledger:{ledger.id}', 'blocked'}

    fix = by_key[f'ledger:{ledger.id}']
    assert fix['resolved_ledger'] == {'id': ledger.id, 'name': _ACCOUNT}
    assert fix['block_reason'] is None
    assert [t['id'] for t in fix['transactions']] == [ok1.id, ok2.id]
    assert all(t['block_reason'] is None for t in fix['transactions'])
    assert all(t['resolved_ledger_id'] == ledger.id for t in fix['transactions'])

    blocked = by_key['blocked']
    assert blocked['resolved_ledger'] is None
    assert blocked['txn_count'] == 2
    reasons = {t['id']: t['block_reason'] for t in blocked['transactions']}
    assert '无名为' in reasons[no_match.id]
    assert '为空' in reasons[no_name.id]
    # 组内原因不一致时组级给概括，逐条真实原因留在 transactions[].block_reason
    assert '逐条' in blocked['block_reason']


def test_txn_display_name_takes_position_name(db, ledger):
    """transactions[].display_name 直取流水快照 position_name；该域 symbol 多为空，名字只能靠它。"""
    named = _mk_txn(db, position_name='2025 年度红利税')
    unnamed = _mk_txn(db)

    data = svc.scan_orphan_ledgers(db, _FAMILY)
    by_id = {x['id']: x for g in data['groups'] for x in g['transactions']}
    assert by_id[named.id]['display_name'] == '2025 年度红利税'
    assert by_id[unnamed.id]['display_name'] is None
    # 契约不变：流水明细里没有 quantity / position_id 等持仓列
    assert 'quantity' not in by_id[named.id]


def test_blocked_group_single_reason_is_specific(db, ledger):
    """blocked 组内原因全同 ⇒ 组级直接给那条具体原因，不套概括话术。"""
    _mk_txn(db, account_name='查无此账本')
    _mk_txn(db, account_name='查无此账本')
    g = svc.scan_orphan_ledgers(db, _FAMILY)['groups'][0]
    assert g['key'] == 'blocked'
    assert '无名为' in g['block_reason']


def test_batches_split_at_600_seconds(db, ledger):
    """按 created_at 聚簇，相邻间隔 > 600 秒切新批；label 取批内首条时间。"""
    _mk_txn(db, created_at=_BASE)
    _mk_txn(db, created_at=_BASE + timedelta(seconds=100))
    _mk_txn(db, created_at=_BASE + timedelta(seconds=800))
    _mk_txn(db, created_at=_BASE + timedelta(seconds=850))

    data = svc.scan_orphan_ledgers(db, _FAMILY)
    assert data['batch_count'] == 2
    b1, b2 = data['batches']
    assert b1 == {'id': 1, 'label': '2026-01-01 09:00', 'txn_count': 2}
    assert b2 == {'id': 2, 'label': '2026-01-01 09:13', 'txn_count': 2}
    assert data['groups'][0]['batch_id'] == 1
    assert data['groups'][0]['batch_label'] == '2026-01-01 09:00'


def test_batch_without_created_at_degrades_label():
    """created_at 为空的流水附到当前批，label 降级 '未知时间'（不编造时间）。

    直接喂 ``_build_batches`` 的纯函数入口：ORM ``TimestampMixin`` 的 created_at 自带
    default，显式传 None 可能被默认值覆盖，从库里读回来就不再是「无时间」；用
    SimpleNamespace 才能稳定覆盖这个降级分支（且零 DB 依赖）。
    """
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(id=1, created_at=_BASE),
        SimpleNamespace(id=2, created_at=None),  # 无时间：附到当前批、不推进时间基准
        SimpleNamespace(id=3, created_at=_BASE + timedelta(seconds=10)),
    ]
    batches, txn_to_batch, batch_labels = svc._build_batches(rows)
    assert batches == [{'id': 1, 'label': '2026-01-01 09:00', 'txn_count': 3}]
    assert set(txn_to_batch.values()) == {1}
    assert batch_labels[1] == '2026-01-01 09:00'

    only_untimed = [SimpleNamespace(id=9, created_at=None)]
    batches2, _, labels2 = svc._build_batches(only_untimed)
    assert batches2 == [{'id': 1, 'label': '未知时间', 'txn_count': 1}]
    assert labels2[1] == '未知时间'


# ── backfill 硬安全约束 ───────────────────────────────────────────────────


def test_backfill_only_updates_ledger_id_and_logs(db, ledger):
    """只 UPDATE ledger_id 一列；审计日志 before/after 逐条记录 null→新值。"""
    t1 = _mk_txn(db, amount_cents=123456)
    t2 = _mk_txn(db, amount_cents=-500)
    before = {t.id: (t.position_id, t.quantity, t.amount, t.symbol, t.account_name) for t in (t1, t2)}

    res = svc.backfill_orphan_ledgers(db, _FAMILY, [t1.id, t2.id], reason='按交割单核对', operator=7)

    assert res['updated'] == 2
    assert res['ledgers'] == [{'id': ledger.id, 'name': _ACCOUNT, 'count': 2}]
    for t in (t1, t2):
        assert t.ledger_id == ledger.id
        assert (t.position_id, t.quantity, t.amount, t.symbol, t.account_name) == before[t.id]

    log = db.query(AdjustmentLog).one()
    assert res['log_id'] == log.id
    assert log.action == 'orphan_ledger_backfill'
    assert log.family_id == _FAMILY
    assert log.reason == '按交割单核对'
    assert log.operator == 7
    assert json.loads(log.before_json) == [
        {'id': t1.id, 'ledger_id': None},
        {'id': t2.id, 'ledger_id': None},
    ]
    assert json.loads(log.after_json) == [
        {'id': t1.id, 'ledger_id': ledger.id},
        {'id': t2.id, 'ledger_id': ledger.id},
    ]
    # 修好后检出集合自熄灭（实时检测，不建状态表）
    assert svc.scan_orphan_ledgers(db, _FAMILY)['total'] == 0


@pytest.mark.parametrize('bad_ids', [None, [], '12', [True], [1.0], ['1'], [None]])
def test_backfill_rejects_invalid_ids(db, ledger, bad_ids):
    """transaction_ids 必须是非空 int 列表；bool 是 int 子类，显式排除。"""
    t = _mk_txn(db)
    with pytest.raises(ValueError):
        svc.backfill_orphan_ledgers(db, _FAMILY, bad_ids)
    assert t.ledger_id is None
    assert db.query(AdjustmentLog).count() == 0


def test_backfill_rejects_over_limit_before_dedupe(db, ledger):
    """上限按去重前的原始条数判定，避免用超长重复列表绕过。"""
    with pytest.raises(ValueError, match='最多 500'):
        svc.backfill_orphan_ledgers(db, _FAMILY, [1] * (svc.MAX_TRANSACTION_IDS + 1))
    assert db.query(AdjustmentLog).count() == 0


def test_backfill_dedupes_ids(db, ledger):
    """重复 id 去重保序，只写一次、审计日志里也只出现一次。"""
    t = _mk_txn(db)
    res = svc.backfill_orphan_ledgers(db, _FAMILY, [t.id, t.id])
    assert res['updated'] == 1
    log = db.query(AdjustmentLog).one()
    assert len(json.loads(log.after_json)) == 1


def test_backfill_rejects_ids_not_in_orphan_set(db, ledger):
    """再次用完整检出条件校验：已修好 / 已挂持仓 / 跨 family 的 id 整体拒绝。"""
    ok = _mk_txn(db)
    fixed = _mk_txn(db, ledger_id=ledger.id)
    attached = _mk_txn(db, position_id=990001)
    foreign = _mk_txn(db, family_id=_OTHER_FAMILY)
    for bad in ([fixed.id], [attached.id], [foreign.id], [ok.id, fixed.id]):
        with pytest.raises(ValueError):
            svc.backfill_orphan_ledgers(db, _FAMILY, bad)
    assert ok.ledger_id is None
    assert db.query(AdjustmentLog).count() == 0


def test_backfill_rejects_blocked_atomically(db, ledger):
    """任一条无法唯一归属 ⇒ 整体 ValueError、零写入（不信任 GET 结果，重新解析）。

    变异探针：若把 ``_plan_backfill`` 里 ``if blocked: raise`` 去掉，本例里可回填
    那条会被写入且审计日志出现，用例失败。
    """
    ok = _mk_txn(db)
    bad = _mk_txn(db, account_name='查无此账本')
    with pytest.raises(ValueError, match='无法唯一归属'):
        svc.backfill_orphan_ledgers(db, _FAMILY, [ok.id, bad.id])
    assert ok.ledger_id is None
    assert bad.ledger_id is None
    assert db.query(AdjustmentLog).count() == 0


# ── undo 幂等 / 留痕 ─────────────────────────────────────────────────────


def test_undo_restores_only_untouched_rows_and_is_idempotent(db, ledger):
    """仅当当前 ledger_id 仍等于 after 值才恢复；被外部改过的行跳过；重复撤销幂等。"""
    a = _mk_txn(db)
    b = _mk_txn(db)
    res = svc.backfill_orphan_ledgers(db, _FAMILY, [a.id, b.id])
    log_id = res['log_id']

    other = _mk_ledger(db, '另一个账户')
    b.ledger_id = other.id  # 外部改动：撤销不得覆盖它
    db.flush()

    out = svc.undo_backfill(db, _FAMILY, log_id)
    assert out == {'restored': 1, 'log_id': log_id}
    assert a.ledger_id is None
    assert b.ledger_id == other.id

    undo_logs = db.query(AdjustmentLog).filter(AdjustmentLog.action == 'orphan_ledger_undo').all()
    assert len(undo_logs) == 1
    assert json.loads(undo_logs[0].before_json) == {'ref_log_id': log_id}
    assert json.loads(undo_logs[0].after_json) == {'restored': 1, 'skipped': 1}

    # 二次撤销：a 已回到 NULL（≠ after），全部跳过
    again = svc.undo_backfill(db, _FAMILY, log_id)
    assert again == {'restored': 0, 'log_id': log_id}
    assert a.ledger_id is None
    assert b.ledger_id == other.id


def test_undo_rejects_wrong_action_or_family(db, ledger):
    """只认本 family 的 orphan_ledger_backfill 日志；log_id 类型也要校验。"""
    log = AdjustmentLog(
        family_id=_FAMILY,
        action='supplement',
        before_json='[]',
        after_json='[]',
    )
    db.add(log)
    db.flush()
    with pytest.raises(ValueError):
        svc.undo_backfill(db, _FAMILY, log.id)  # 非本 action
    with pytest.raises(ValueError):
        svc.undo_backfill(db, _OTHER_FAMILY, log.id)  # 跨 family
    with pytest.raises(ValueError):
        svc.undo_backfill(db, _FAMILY, True)  # bool 不是合法 id
    with pytest.raises(ValueError):
        svc.undo_backfill(db, _FAMILY, 999999)  # 不存在
    assert db.query(AdjustmentLog).filter(AdjustmentLog.action == 'orphan_ledger_undo').count() == 0


def test_undo_rejects_corrupt_log_json(db, ledger):
    """审计日志 JSON 损坏 / 结构异常 ⇒ ValueError，不写任何东西。"""
    broken = AdjustmentLog(
        family_id=_FAMILY,
        action='orphan_ledger_backfill',
        before_json='{not-json',
        after_json='[]',
    )
    db.add(broken)
    db.flush()
    with pytest.raises(ValueError, match='JSON 损坏'):
        svc.undo_backfill(db, _FAMILY, broken.id)

    not_list = AdjustmentLog(
        family_id=_FAMILY,
        action='orphan_ledger_backfill',
        before_json='{"id": 1}',
        after_json='[]',
    )
    db.add(not_list)
    db.flush()
    with pytest.raises(ValueError, match='结构异常'):
        svc.undo_backfill(db, _FAMILY, not_list.id)
    assert db.query(AdjustmentLog).filter(AdjustmentLog.action == 'orphan_ledger_undo').count() == 0

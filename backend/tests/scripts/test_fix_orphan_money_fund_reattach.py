# -*- coding: utf-8 -*-
"""fix_orphan_money_fund_reattach 脚本单测（#1657）。

原 PR 只在 tests/services 覆盖了运行时两条写入路径，**没有一例跑那个脚本**——
而脚本正是本次唯一在真实库 `--apply` 过的组件。本文件补齐脚本侧。

覆盖：
- 正向：跨形态代码（`SZ001937` ↔ `001937`）双向命中——脚本曾用 `symbol` 精确相等
  而静默漏挂的那一类；
- 反向：收益行 / 非现金等价物类型 / 跨 ledger / 跨 family / 已挂回 一律不命中；
- 归一化不出 6 位数字的 symbol 不参与匹配（避免空串把不相干孤儿流水一起吸走）；
- 同一 (ledger, family, 代码) 命中多个持仓 → 跳过并报告，不猜；
- dry-run 零写入；`--apply` 落库且幂等；`--db` 缺失 / 文件不存在 的退出码；
- `emit_sql` 正向与反向逐行对应，被跳过的项不得出现在 SQL 里。

夹具用临时 SQLite 文件 + **真实 ORM 表结构**（`__table__.create`），直接 insert 行，
使脚本 `open_session` 走的是它自己的引擎——与线上调用路径一致。
"""

import os
import sqlite3
import sys

import pytest
from sqlalchemy import create_engine

_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import fix_orphan_money_fund_reattach as m  # noqa: E402

from app.domains.positions.models import Position  # noqa: E402
from app.domains.transactions.models import Transaction  # noqa: E402


@pytest.fixture
def db_file(tmp_path):
    """建一个只含 positions / transactions 两张真表的临时库（其余表用不到）。"""
    path = tmp_path / 'invest.db'
    engine = create_engine(f'sqlite:///{path.as_posix()}')
    Transaction.__table__.create(engine)
    Position.__table__.create(engine)
    engine.dispose()
    return path


def _seed(db_file, positions=(), txns=()):
    """用 ORM 造数。

    刻意不用 raw INSERT：`positions.source` / `ownership_status` 是 NOT NULL 且只有
    **Python 侧**默认值（无 server_default），裸 SQL 会直接 IntegrityError。
    """
    db = m.open_session(db_file)
    try:
        for pid, symbol, ledger_id, family_id in positions:
            db.add(Position(id=pid, symbol=symbol, ledger_id=ledger_id, family_id=family_id))
        for tid, symbol, asset_type, txn_type, ledger_id, family_id, is_income, position_id, amount in txns:
            db.add(
                Transaction(
                    id=tid,
                    symbol=symbol,
                    asset_type=asset_type,
                    txn_type=txn_type,
                    ledger_id=ledger_id,
                    family_id=family_id,
                    is_income=None if is_income is None else bool(is_income),
                    position_id=position_id,
                    amount=amount,
                )
            )
        db.commit()
    finally:
        db.close()


def _position_ids(db_file):
    """{txn_id: position_id}，用于断言写入结果。"""
    conn = sqlite3.connect(str(db_file))
    try:
        return dict(conn.execute('SELECT id, position_id FROM transactions').fetchall())
    finally:
        conn.close()


def _drain(db_file):
    """跑一遍 dry-run，返回 stdout（capsys 版见各用例）。"""
    return m.main(['--db', str(db_file)])


# ── 正向：跨形态代码 ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('pos_symbol', 'txn_symbol'),
    [
        ('001937', 'SZ001937'),  # 持仓裸码 / 流水带前缀
        ('SZ001937', '001937'),  # 持仓带前缀 / 流水裸码
        ('001937', '001937'),  # 两侧裸码（本机 3 个成功案例正是这种，掩盖了原缺陷）
        ('sh.001937', '001937'),  # 带分隔符写法
    ],
)
def test_scan_matches_across_symbol_forms(db_file, pos_symbol, txn_symbol):
    """归一化后相等即命中——这是"脚本与运行时同源"的核心断言。"""
    _seed(
        db_file,
        positions=[(445, pos_symbol, 20, 1)],
        txns=[(1649, txn_symbol, 'money_fund', 'buy', 20, 1, 0, None, 397361)],
    )

    with m.open_session(db_file) as db:
        result = m.scan(db)

    assert len(result.targets) == 1
    target = result.targets[0]
    assert target.position_id == 445
    assert [row[0] for row in target.orphan_txns] == [1649]


def test_scan_matches_reverse_repo_too(db_file):
    """逆回购同属现金等价物桶，同样要补挂回。"""
    _seed(
        db_file, positions=[(9, '204001', 20, 1)], txns=[(7, '204001', 'reverse_repo', 'buy', 20, 1, 0, None, 100000)]
    )

    with m.open_session(db_file) as db:
        result = m.scan(db)

    assert [t.position_id for t in result.targets] == [9]


# ── 反向：不得命中 ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('txn', 'why'),
    [
        ((31, None, 'money_fund', 'buy', 20, 1, 0, None, 100), '无 symbol'),
        ((32, '999999', 'money_fund', 'buy', 20, 1, 0, None, 100), '无同名持仓'),
        ((33, '001937', 'stock', 'buy', 20, 1, 0, None, 100), '非现金等价物类型'),
        ((34, '001937', 'money_fund', 'buy', 7, 1, 0, None, 100), '跨 ledger'),
        ((35, '001937', 'money_fund', 'buy', 20, 2, 0, None, 100), '跨 family'),
        ((36, '001937', 'money_fund', 'buy', 20, 1, 1, None, 100), '收益行（#863 D1 不挂回）'),
        ((37, '001937', 'money_fund', 'buy', 20, 1, 0, 445, 100), '已挂回，不在扫描范围'),
    ],
)
def test_scan_ignores_non_candidates(db_file, txn, why):
    _seed(db_file, positions=[(445, '001937', 20, 1)], txns=[txn])

    with m.open_session(db_file) as db:
        result = m.scan(db)

    assert result.targets == [], f'{why} 不应成为候选'


def test_scan_ignores_symbols_without_six_digit_code(db_file):
    """归一化不出 6 位数字的 symbol 不参与：否则空串会与同样归一化失败的流水互相匹配。"""
    _seed(
        db_file,
        positions=[(1, 'CASH', 20, 1)],
        txns=[(11, 'CASH', 'money_fund', 'buy', 20, 1, 0, None, 100)],
    )

    with m.open_session(db_file) as db:
        result = m.scan(db)

    assert result.targets == []


def test_find_orphan_cash_flows_returns_empty_for_unparsable_symbol():
    """直接对运行时同一函数断言空码短路（脚本与写入层共用此函数）。"""
    from app.services.position_service import find_orphan_cash_flows

    assert find_orphan_cash_flows(object(), 20, 'CASH', 1) == []
    assert find_orphan_cash_flows(object(), 20, '', 1) == []


# ── 多持仓歧义 ──────────────────────────────────────────────────────


def test_scan_skips_ambiguous_multiple_positions(db_file):
    """同 (ledger, family, 代码) 有 2 个持仓 → 跳过并报告，不替人做决定。"""
    _seed(
        db_file,
        positions=[(445, '001937', 20, 1), (446, 'SZ001937', 20, 1)],
        txns=[(1649, '001937', 'money_fund', 'buy', 20, 1, 0, None, 100)],
    )

    with m.open_session(db_file) as db:
        result = m.scan(db)

    assert result.targets == []
    assert result.skipped_ambiguous == [(445, '001937', 2)]


def test_scan_counts_positions_without_ledger(db_file):
    _seed(db_file, positions=[(1, '001937', None, 1)], txns=[])

    with m.open_session(db_file) as db:
        result = m.scan(db)

    assert result.skipped_no_ledger == 1
    assert result.targets == []


# ── dry-run / apply ─────────────────────────────────────────────────


def test_dry_run_writes_nothing(db_file, capsys):
    _seed(
        db_file, positions=[(445, '001937', 20, 1)], txns=[(1649, '001937', 'money_fund', 'buy', 20, 1, 0, None, 100)]
    )

    assert _drain(db_file) == 0

    out = capsys.readouterr().out
    assert 'dry-run' in out
    assert 'txn#1649' in out  # 必须列出具体 txn.id，否则无法人工复核
    assert _position_ids(db_file) == {1649: None}


def test_apply_writes_and_is_idempotent(db_file, capsys):
    _seed(
        db_file, positions=[(445, '001937', 20, 1)], txns=[(1649, 'SZ001937', 'money_fund', 'buy', 20, 1, 0, None, 100)]
    )

    assert m.main(['--db', str(db_file), '--apply']) == 0
    assert _position_ids(db_file) == {1649: 445}

    # 幂等：再跑一次应报「已干净」且不再改动
    capsys.readouterr()
    assert m.main(['--db', str(db_file), '--apply']) == 0
    assert '数据库已干净' in capsys.readouterr().out
    assert _position_ids(db_file) == {1649: 445}


def test_cli_requires_db_and_rejects_missing_file(tmp_path):
    with pytest.raises(SystemExit):
        m.main([])
    assert m.main(['--db', str(tmp_path / 'nope.db')]) == 2


# ── SQL 输出 ────────────────────────────────────────────────────────


def test_emit_sql_pairs_forward_and_reverse(db_file):
    _seed(
        db_file,
        positions=[(445, '001937', 20, 1), (9, '204001', 20, 1)],
        txns=[
            (1649, 'SZ001937', 'money_fund', 'buy', 20, 1, 0, None, 100),
            (1650, '001937', 'money_fund', 'deposit', 20, 1, 0, None, 200),
            (7, '204001', 'reverse_repo', 'buy', 20, 1, 0, None, 300),
        ],
    )

    with m.open_session(db_file) as db:
        targets = m.scan(db).targets

    sql = m.emit_sql(targets)
    assert 'UPDATE transactions SET position_id = 445 WHERE id = 1649 AND position_id IS NULL;' in sql
    assert 'UPDATE transactions SET position_id = 445 WHERE id = 1650 AND position_id IS NULL;' in sql
    assert 'UPDATE transactions SET position_id = 9 WHERE id = 7 AND position_id IS NULL;' in sql
    # 反向段逐行对应
    for txn_id in (1649, 1650, 7):
        assert f'UPDATE transactions SET position_id = NULL WHERE id = {txn_id};' in sql


def test_emit_sql_excludes_skipped_targets(db_file):
    """被跳过的歧义项不得出现在 SQL 里（否则人工照抄即误改数据）。

    歧义用「裸码 + 带前缀」构造——真表有 `UNIQUE(ledger_id, symbol)`，两个字面量不同的
    symbol 归一化到同一代码时才可能并存，这也正是该分支在现实中唯一可达的形态。
    """
    _seed(
        db_file,
        positions=[(445, '001937', 20, 1), (446, 'SZ001937', 20, 1)],
        txns=[(1649, '001937', 'money_fund', 'buy', 20, 1, 0, None, 100)],
    )

    with m.open_session(db_file) as db:
        result = m.scan(db)

    sql = m.emit_sql(result.targets)
    assert 'SET position_id' not in sql
    assert '1649' not in sql


def test_rollback_out_written_only_on_request(db_file, tmp_path):
    _seed(
        db_file, positions=[(445, '001937', 20, 1)], txns=[(1649, '001937', 'money_fund', 'buy', 20, 1, 0, None, 100)]
    )
    out = tmp_path / 'rollback.sql'

    assert m.main(['--db', str(db_file), '--rollback-out', str(out)]) == 0
    text = out.read_text(encoding='utf-8')
    assert 'position_id = 445 WHERE id = 1649' in text
    assert 'position_id = NULL WHERE id = 1649' in text
    assert _position_ids(db_file) == {1649: None}  # 写 SQL 文件不等于写库

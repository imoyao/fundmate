# -*- coding: utf-8 -*-
"""清理脚本 clean_daily_worth_money_fund_misrouted 的单测（#1554）。

覆盖三类：
- 正向：11 只孤立错表行被精确命中；
- 反向：普通基金 / 非目标日期 / 有真实序列的场内货币一律不动；
- 防过度抑制：`--apply` 后其他基金与其他日期零影响，且回滚 SQL 可完整重放还原。
"""

import os
import sqlite3
import sys

import pytest

_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import clean_daily_worth_money_fund_misrouted as m  # noqa: E402

TARGET_DATE = '2026-08-29'

# #1554 卡内的 11 只错表货基
_MISROUTED = [
    '000379',
    '000509',
    '001010',
    '001821',
    '001937',
    '003003',
    '004369',
    '007866',
    '026029',
    '040003',
    '121011',
]
# 场内货币：daily_worth 里有真实净值序列，必须豁免（卡内明确要求保留）
_INTRADAY_MONEY = '003816'
# 普通基金：同一天也有净值行，但不是货基，不得命中
_NORMAL_FUND = '110011'
# 货基，但只有非目标日的行
_OTHER_DATE_MONEY = '999999'


def _make_db(conn: sqlite3.Connection) -> None:
    conn.execute('CREATE TABLE funds (fund_code VARCHAR(6) PRIMARY KEY, name VARCHAR, fund_type_id INTEGER)')
    conn.execute(
        'CREATE TABLE daily_worth ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, fund_code VARCHAR(6), date DATE, '
        'unit_nav NUMERIC, acc_nav NUMERIC, created_at DATETIME, updated_at DATETIME)'
    )
    funds = [(c, '货基%s' % c, m.MONEY_FUND_TYPE_ID) for c in _MISROUTED]
    funds += [(_INTRADAY_MONEY, '银华日利B', m.MONEY_FUND_TYPE_ID)]
    funds += [(_OTHER_DATE_MONEY, '另一货基', m.MONEY_FUND_TYPE_ID)]
    funds += [(_NORMAL_FUND, '易方达中小盘', 1)]
    conn.executemany('INSERT INTO funds (fund_code, name, fund_type_id) VALUES (?,?,?)', funds)

    rows = [
        (c, TARGET_DATE, '1.0', '1.0', '2026-08-29 21:55:46.171887', '2026-08-29 21:55:46.171887') for c in _MISROUTED
    ]
    # 场内货币：目标日也有 1 行，但本表另有 5 行真实序列 → 共 6 行，属真实净值序列，必须豁免
    rows += [(_INTRADAY_MONEY, TARGET_DATE, '1.0', '1.0', '2026-08-06 10:00:00', '2026-08-06 10:00:00')]
    rows += [
        (_INTRADAY_MONEY, '2026-08-0%d' % d, '1.0', '1.0', '2026-08-06 10:00:00', '2026-08-06 10:00:00')
        for d in range(1, 6)
    ]
    # 普通基金在同一目标日的正常净值
    rows += [(_NORMAL_FUND, TARGET_DATE, '3.5', '4.2', '2026-08-30 10:00:00', '2026-08-30 10:00:00')]
    # 货基但日期不是目标日
    rows += [(_OTHER_DATE_MONEY, '2026-08-30', '1.0', '1.0', '2026-08-31 10:00:00', '2026-08-31 10:00:00')]
    conn.executemany(
        'INSERT INTO daily_worth (fund_code, date, unit_nav, acc_nav, created_at, updated_at) VALUES (?,?,?,?,?,?)',
        rows,
    )
    conn.commit()


def _snapshot(conn: sqlite3.Connection) -> list:
    return sorted(
        conn.execute(
            'SELECT id, fund_code, date, unit_nav, acc_nav, created_at, updated_at FROM daily_worth'
        ).fetchall()
    )


@pytest.fixture()
def conn():
    c = sqlite3.connect(':memory:')
    c.isolation_level = None
    _make_db(c)
    try:
        yield c
    finally:
        c.close()


# ─────────────── 正向 ───────────────


def test_collect_hits_exactly_11_isolated_rows(conn):
    targets, exempt = m.collect_candidates(conn, TARGET_DATE)
    assert sorted(r['fund_code'] for r in targets) == sorted(_MISROUTED)
    assert len(targets) == 11
    assert all(r['rows_in_table'] == 1 for r in targets)
    # 错表形态：unit_nav = acc_nav = 面值 1.0（SQLite NUMERIC 亲和可能存成 int，故按数值比）
    assert all(float(r['unit_nav']) == 1.0 and float(r['acc_nav']) == 1.0 for r in targets)
    assert len(exempt) == 1


# ─────────────── 反向：不得误伤 ───────────────


def test_collect_exempts_intraday_money_with_real_series(conn):
    """场内货币（本表有多行真实序列）即使 fund_type_id=6 也必须豁免。"""
    targets, exempt = m.collect_candidates(conn, TARGET_DATE)
    assert _INTRADAY_MONEY not in {r['fund_code'] for r in targets}
    assert [r['fund_code'] for r in exempt] == [_INTRADAY_MONEY]
    assert exempt[0]['rows_in_table'] == 6


def test_collect_ignores_normal_fund_same_date(conn):
    """同一天有净值的普通基金（fund_type_id != 6）不得命中。"""
    targets, exempt = m.collect_candidates(conn, TARGET_DATE)
    assert _NORMAL_FUND not in {r['fund_code'] for r in targets}
    assert _NORMAL_FUND not in {r['fund_code'] for r in exempt}


def test_collect_respects_target_date(conn):
    """货基在非目标日期的行不得命中（清理限定在目标日一天内）。"""
    targets, exempt = m.collect_candidates(conn, TARGET_DATE)
    assert _OTHER_DATE_MONEY not in {r['fund_code'] for r in targets}
    assert _OTHER_DATE_MONEY not in {r['fund_code'] for r in exempt}


# ─────────────── 执行与防过度抑制 ───────────────


def test_purge_deletes_11_and_touches_nothing_else(conn):
    targets, _ = m.collect_candidates(conn, TARGET_DATE)
    before_total = conn.execute('SELECT COUNT(*) FROM daily_worth').fetchone()[0]
    unchanged = _snapshot(conn)
    keep = [r for r in unchanged if r[1] in (_INTRADAY_MONEY, _NORMAL_FUND, _OTHER_DATE_MONEY)]

    deleted = m.purge(conn, targets)
    assert deleted == 11

    after_total = conn.execute('SELECT COUNT(*) FROM daily_worth').fetchone()[0]
    assert before_total - after_total == 11
    assert [r for r in _snapshot(conn) if r[1] in (_INTRADAY_MONEY, _NORMAL_FUND, _OTHER_DATE_MONEY)] == keep

    # 幂等：再收集应为空
    left, left_exempt = m.collect_candidates(conn, TARGET_DATE)
    assert left == []
    assert [r['fund_code'] for r in left_exempt] == [_INTRADAY_MONEY]


def test_purge_rolls_back_when_count_mismatch(conn):
    """DELETE 影响行数不符预期时必须整体回滚（#1554 防误删的兜底）。"""
    before = _snapshot(conn)
    bogus = [{'id': 999999, 'fund_code': '000379', 'date': TARGET_DATE}]
    with pytest.raises(RuntimeError, match='删除条数校验失败'):
        m.purge(conn, bogus)
    assert _snapshot(conn) == before


# ─────────────── 回滚 SQL 可重放 ───────────────


def test_rollback_sql_replays_to_original_state(conn):
    """回滚 SQL 必须能把库完整还原到清理前（本脚本以此替代全库副本）。"""
    targets, _ = m.collect_candidates(conn, TARGET_DATE)
    before = _snapshot(conn)

    sql = m.rollback_sql(targets, TARGET_DATE)
    m.purge(conn, targets)
    assert len(_snapshot(conn)) == len(before) - 11

    for stmt in [s for s in sql.splitlines() if s.strip() and not s.strip().startswith('--')]:
        conn.execute(stmt.split(';')[0])

    assert _snapshot(conn) == before


# ─────────────── CLI ───────────────


def test_cli_dry_run_makes_no_change(conn, tmp_path, monkeypatch):
    db_file = tmp_path / 'invest.db'
    src = sqlite3.connect(str(db_file))
    try:
        _make_db(src)
    finally:
        src.close()
    before = _snapshot(sqlite3.connect(str(db_file)))

    monkeypatch.setattr(sys, 'argv', ['clean', '--db', str(db_file)])
    assert m.main() == 0
    assert _snapshot(sqlite3.connect(str(db_file))) == before


def test_cli_apply_cleans_and_is_reentrant(conn, tmp_path, monkeypatch):
    db_file = tmp_path / 'invest.db'
    src = sqlite3.connect(str(db_file))
    try:
        _make_db(src)
    finally:
        src.close()

    monkeypatch.setattr(sys, 'argv', ['clean', '--db', str(db_file), '--apply'])
    assert m.main() == 0
    after = sqlite3.connect(str(db_file))
    try:
        remaining = after.execute(
            'SELECT d.fund_code FROM daily_worth d JOIN funds f ON f.fund_code = d.fund_code '
            'WHERE f.fund_type_id = 6 AND d.date = ? ORDER BY d.fund_code',
            (TARGET_DATE,),
        ).fetchall()
        # 11 只孤立错点已清零；唯一残留在目标日的货基行是豁免的场内货币
        assert [r[0] for r in remaining] == [_INTRADAY_MONEY]
        assert (
            after.execute('SELECT COUNT(*) FROM daily_worth WHERE fund_code = ?', (_INTRADAY_MONEY,)).fetchone()[0] == 6
        )
    finally:
        after.close()

    # 再跑一次：已清理过，应走「无需清理」分支且不报错
    monkeypatch.setattr(sys, 'argv', ['clean', '--db', str(db_file), '--apply'])
    assert m.main() == 0

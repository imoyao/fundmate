# -*- coding: utf-8 -*-
"""回填脚本 backfill_ledger_type_from_category 的单测。

覆盖三件容易写错的事：

1. **只改真不一致的行**，且不碰 ``channel_category IS NULL``（拿「默认值」改用户数据是误伤）；
2. **apply 后库内其余列/表一行不动**，并留下可回灌 SQL；
3. **断言真的会拦**——故意把计划里的目标值改错，必须整体回滚（探针，不是装饰）。
"""

import os
import sqlite3
import sys
from pathlib import Path

_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import backfill_ledger_type_from_category as m  # noqa: E402

_CONSERVED_DDL = {
    'positions': 'CREATE TABLE positions (id INTEGER PRIMARY KEY, ledger_id INTEGER)',
    'assets': 'CREATE TABLE assets (id INTEGER PRIMARY KEY, ledger_id INTEGER)',
    'transactions': 'CREATE TABLE transactions (id INTEGER PRIMARY KEY, ledger_id INTEGER)',
    'asset_snapshots': 'CREATE TABLE asset_snapshots (id INTEGER PRIMARY KEY, ledger_id INTEGER)',
    'pnl_daily_snapshots': 'CREATE TABLE pnl_daily_snapshots (id INTEGER PRIMARY KEY, ledger_id INTEGER)',
    'position_import_meta': 'CREATE TABLE position_import_meta (id INTEGER PRIMARY KEY, ledger_id INTEGER)',
}


def _make_db(rows):
    """最小库：ledgers 全列 + 六张「必须守恒」的表（空表即可，行数守恒断言照样生效）。"""
    conn = sqlite3.connect(':memory:')
    conn.execute(
        'CREATE TABLE ledgers ('
        'id INTEGER PRIMARY KEY, name VARCHAR, ledger_type VARCHAR, channel_category VARCHAR, '
        'family_id INTEGER, sales_institution_id INTEGER, notes VARCHAR)'
    )
    for ddl in _CONSERVED_DDL.values():
        conn.execute(ddl)
    conn.executemany(
        'INSERT INTO ledgers (id, name, ledger_type, channel_category, family_id, sales_institution_id, notes) '
        'VALUES (?,?,?,?,?,?,?)',
        rows,
    )
    conn.commit()
    return conn


def test_plan_只挑出类型与渠道类别矛盾的行():
    conn = _make_db(
        [
            (22, '浦发银行', 'fund', 'bank', 1, 9, None),
            (23, '招商银行', 'fund', 'bank', 1, 4, None),
            (24, '上海陆金所基金销售', 'fund', 'fund_platform', 1, 340, None),
        ]
    )
    p = m.plan(conn)
    assert [c['id'] for c in p.changes] == [22, 23]
    assert {c['id']: c['_expected'] for c in p.changes} == {22: 'bank', 23: 'bank'}
    assert p.skipped == []


def test_plan_跳过channel_category为空的行():
    conn = _make_db([(17, '富国基金', 'fund', None, 1, None, None)])
    p = m.plan(conn)
    # 空渠道类别拿不到「该是什么」，一律不动——映射函数对 None 返回 bank，那是安全默认，不是事实
    assert p.changes == []
    assert p.skipped == []


def test_plan_跳过反向不唯一的渠道类别_真实案例住房信息记录():
    """`channel_category='other'` 反推对应 property/e_account/family 三种，派生值不是事实。

    实测：本地库 #8「住房信息记录」ledger_type=property、channel_category=other，
    若按正向映射会被改成 bank —— 房产账户按银行口径算（现金 + 关联负债 + 货基占比），
    既错又没人会发现。
    """
    conn = _make_db([(8, '住房信息记录', 'property', 'other', 1, None, None)])
    p = m.plan(conn)
    assert p.changes == []
    assert [r['id'] for r, _ in p.skipped] == [8]
    assert '反向对应多个 ledger_type' in p.skipped[0][1]


def test_反向不唯一集合由回退表现算_不是写死other():
    """判据从 LEDGER_TYPE_TO_CHANNEL_CATEGORY_FALLBACK 现算，表改了判据跟着改。"""
    assert 'other' in m.AMBIGUOUS_CHANNEL_CATEGORIES
    # 唯一反向的渠道类别不能被误判成不唯一（否则 #22/#23 就修不掉了）
    assert 'bank' not in m.AMBIGUOUS_CHANNEL_CATEGORIES
    assert 'fund_platform' not in m.AMBIGUOUS_CHANNEL_CATEGORIES
    assert 'securities' not in m.AMBIGUOUS_CHANNEL_CATEGORIES


def test_plan_跳过未知的当前类型():
    conn = _make_db([(99, '遗留账户', 'legacy_kind', 'bank', 1, None, None)])
    p = m.plan(conn)
    assert p.changes == []
    assert [r['id'] for r, _ in p.skipped] == [99]
    assert '不在允许集合内' in p.skipped[0][1]


def test_apply_只改一列_其余列与其余表不动_并留下回灌脚本(tmp_path):
    conn = _make_db(
        [
            (22, '浦发银行', 'fund', 'bank', 1, 9, '原备注'),
            (24, '上海陆金所基金销售', 'fund', 'fund_platform', 1, 340, None),
        ]
    )
    backup = tmp_path / 'backup.sql'
    m.apply_plan(conn, m.plan(conn), backup)

    row = conn.execute(
        'SELECT ledger_type, name, channel_category, family_id, sales_institution_id, notes FROM ledgers WHERE id = 22'
    ).fetchone()
    assert tuple(row) == ('bank', '浦发银行', 'bank', 1, 9, '原备注')
    # 一致的行不该被顺手改写
    assert conn.execute('SELECT ledger_type FROM ledgers WHERE id = 24').fetchone()[0] == 'fund'

    sql = backup.read_text(encoding='utf-8')
    assert 'INSERT INTO ledgers' in sql
    assert "'浦发银行'" in sql and 'fund' in sql  # 回灌的是改动前的整行

    # 幂等：再跑一遍不该有任何候选
    assert m.plan(conn).changes == []


def test_apply_断言会拦住错误的目标值_并整体回滚(tmp_path):
    """探针：把计划里的目标值改错，必须报错且库保持原样（否则断言只是装饰）。"""
    conn = _make_db([(22, '浦发银行', 'fund', 'bank', 1, 9, None)])
    p = m.plan(conn)
    p.changes[0]['_expected'] = 'fund'  # 改回原值 → 与判据不一致，断言应触发

    try:
        m.apply_plan(conn, p, tmp_path / 'backup.sql')
    except AssertionError as exc:
        assert '拒绝执行' in str(exc) or '未收敛' in str(exc)
    else:  # pragma: no cover
        raise AssertionError('断言没有触发——回填脚本失去了唯一的兜底')

    assert conn.execute('SELECT ledger_type FROM ledgers WHERE id = 22').fetchone()[0] == 'fund'


def test_读不到守恒表时中止而不是当成零():
    conn = sqlite3.connect(':memory:')
    conn.execute(
        'CREATE TABLE ledgers ('
        'id INTEGER PRIMARY KEY, name VARCHAR, ledger_type VARCHAR, channel_category VARCHAR, '
        'family_id INTEGER, sales_institution_id INTEGER, notes VARCHAR)'
    )
    conn.execute("INSERT INTO ledgers VALUES (22, '浦发银行', 'fund', 'bank', 1, 9, NULL)")
    conn.commit()

    try:
        m.apply_plan(conn, m.plan(conn), Path(os.devnull))
    except SystemExit as exc:
        assert 'positions' in str(exc)
    else:  # pragma: no cover
        raise AssertionError('缺表时不得静默当成 0 行')

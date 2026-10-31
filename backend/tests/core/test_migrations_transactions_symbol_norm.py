# -*- coding: utf-8 -*-
"""#1662 遗留项 回归：transactions.symbol_norm 归一身份列 + asset_type 回填迁移。

## 这张卡要钉住的是什么

#1662 的结论「唯一约束挂在身份而非字面量」当时只落在 `positions`（#1677 / PR #1680），
`transactions` 被漏掉。后果不是「少一个字段」，而是**读侧静默漏算**：本机实测持仓
`001937`、流水 `SZ001937`，而 `Transaction.symbol == position.symbol` 是字面量等值。

故本文件的核心不是「列加上了没有」，而是：

1. `asset_type` 为 NULL 的流水能按**确定性判据**补出来（position 关联 / 名录+名称一致）；
2. 补出 `asset_type` 后，带前缀的场外码与持仓裸码收敛到**同一个身份**；
3. 名称是判据的一部分 —— `000638` 在场外是「富国富钱包货币A」、在深市是「*ST万方」，
   名录命中不足以定性，名称不符时必须**拒绝回填**（宁可留空给审计，不能猜）；
4. 幂等（二次 `[SKIP]`）、空库安全、无 symbol 的现金流水不动；
5. PG（生产 user 域）不早退，DDL 是 PG 能吃的形态。
"""

import sqlite3

from sqlalchemy import create_engine, inspect, text

from app.core.migrations import migrate_transactions_symbol_norm

from .migrations_pg_fake import PgFake


def _make_old_db(path, txn_rows, pos_rows=(), fund_rows=()):
    """造一个「加 symbol_norm 列之前」的库（列名取真实 schema 的子集）。

    ⚠️ `type` 是 asset_type 的**实际库列名**（ORM 里 `asset_type = Column('type', ...)`），
    不是笔误 —— 迁移与测试都按 `type` 取值。
    `fund_types.id = 6` 是「货币型」（与真实名录一致）。
    """
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY,
            symbol VARCHAR(30) NOT NULL,
            type VARCHAR(20),
            ledger_id INTEGER,
            family_id INTEGER,
            symbol_norm VARCHAR(64) NOT NULL DEFAULT ''
        );
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            symbol VARCHAR(30),
            asset_type VARCHAR(20),
            position_name VARCHAR(100),
            position_id INTEGER,
            ledger_id INTEGER,
            family_id INTEGER
        );
        CREATE TABLE fund_types (
            id INTEGER PRIMARY KEY,
            name VARCHAR(20),
            variety_id INTEGER
        );
        CREATE TABLE funds (
            fund_code VARCHAR(10) PRIMARY KEY,
            name VARCHAR(100),
            fund_type_id INTEGER
        );
        """
    )
    conn.execute("INSERT INTO fund_types(id, name, variety_id) VALUES (1, '混合型', 1), (6, '货币型', 6)")
    if fund_rows:
        conn.executemany('INSERT INTO funds(fund_code, name, fund_type_id) VALUES (?, ?, ?)', fund_rows)
    if pos_rows:
        conn.executemany('INSERT INTO positions(id, symbol, type, ledger_id, family_id) VALUES (?, ?, ?, ?, ?)', pos_rows)
    conn.executemany(
        'INSERT INTO transactions(id, symbol, asset_type, position_name, position_id, ledger_id, family_id) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        txn_rows,
    )
    conn.commit()
    conn.close()


def _engine_for(path):
    # Windows 上 as_posix() 才与 SQLAlchemy 的 sqlite URL 约定一致（反斜杠会解析异常）
    return create_engine(f'sqlite:///{path.as_posix()}')


def _rows(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).fetchall()


def test_backfills_asset_type_from_fund_directory_and_collapses_prefix(tmp_path):
    """无 position 关联时按名录+名称回填，带前缀的场外码收敛到裸码身份。"""
    db = tmp_path / 'invest.db'
    _make_old_db(
        db,
        txn_rows=[
            # (id, symbol, asset_type, position_name, position_id, ledger_id, family_id)
            (1, 'SZ001937', None, '兴银现金增利货币', None, 1, 1),
            (2, 'SZ011341', None, '博时战略新材料主题混合C', None, 1, 1),
        ],
        fund_rows=[
            ('001937', '兴银现金增利货币', 6),
            ('011341', '博时战略新材料主题混合C', 1),
        ],
    )
    engine = _engine_for(db)

    assert migrate_transactions_symbol_norm(engine).startswith('[OK]')

    assert {c['name'] for c in inspect(engine).get_columns('transactions')} >= {'symbol_norm'}
    got = dict(_rows(engine, 'SELECT symbol, symbol_norm FROM transactions'))
    # 带前缀的场外码必须收敛到裸码身份（这正是读侧能重新匹配上的原因）
    assert got == {'SZ001937': 'OTC:001937', 'SZ011341': 'OTC:011341'}
    # 货币型 → money_fund；混合型 → fund（不能用同一个值糊过去）
    assert dict(_rows(engine, 'SELECT symbol, asset_type FROM transactions')) == {
        'SZ001937': 'money_fund',
        'SZ011341': 'fund',
    }


def test_asset_type_from_position_link_wins(tmp_path):
    """position_id 可关联时优先取持仓类型（同一笔交易自己的类型，最强信号）。"""
    db = tmp_path / 'invest.db'
    _make_old_db(
        db,
        txn_rows=[(1, 'SZ016462', None, '华宝生态中国混合C', 16, 1, 1)],
        pos_rows=[(16, '016462', 'fund', 1, 1)],
        # 名录里故意给个**相反**的类型，验证优先序：持仓赢了才说明判据顺序生效
        fund_rows=[('016462', '华宝生态中国混合C', 6)],
    )
    engine = _engine_for(db)

    assert migrate_transactions_symbol_norm(engine).startswith('[OK]')
    assert _rows(engine, 'SELECT asset_type, symbol_norm FROM transactions') == [('fund', 'OTC:016462')]


def test_name_mismatch_refuses_backfill(tmp_path):
    """名录命中但名称不符 → **拒绝**回填，不猜。

    `000638` 是真实的同名段冲突：场外是「富国富钱包货币A」、深市是「*ST万方」。
    仅凭 `funds` 命中就判成基金，会把一笔真股票流水改成 `OTC:000638` —— 数据被改坏且不可逆。
    """
    db = tmp_path / 'invest.db'
    _make_old_db(
        db,
        txn_rows=[
            (1, 'SZ000638', None, '富国富钱包货币A', None, 1, 1),  # 名称一致 → 回填
            (2, 'SZ000638', None, '*ST万方', None, 1, 1),  # 名称不符 → 拒绝
        ],
        fund_rows=[('000638', '富国富钱包货币A', 6)],
    )
    engine = _engine_for(db)

    result = migrate_transactions_symbol_norm(engine)
    assert result.startswith('[OK]')
    assert '1 行 asset_type 待人工确认' in result

    got = dict(_rows(engine, 'SELECT id, asset_type FROM transactions'))
    assert got[1] == 'money_fund'
    assert got[2] is None  # 未被猜成 fund

    norms = dict(_rows(engine, 'SELECT id, symbol_norm FROM transactions'))
    assert norms[1] == 'OTC:000638'
    # 未定性的那行只能是降级形态（与持仓身份不等），不能伪装成已收敛
    assert norms[2] == 'NO_VENUE:SZ000638'


def test_cash_and_null_symbol_rows_untouched(tmp_path):
    """无 symbol 的现金/账户流水不该被写进任何身份（也不能反复重算）。

    `__CASH__` 是账户级资金流水的哨兵 symbol（有值但不是标的），它落到
    `NO_VENUE:__CASH__` 是既定语义 —— `cash` 不在 `asset_type → venue` 表里，
    `venue_of_row` 如实返回 NO_VENUE 而非猜一个场所。这里一并钉住，避免将来
    有人为了「看起来整齐」把它特判成空串。
    """
    db = tmp_path / 'invest.db'
    _make_old_db(
        db,
        txn_rows=[
            (1, None, 'cash', '现金存入', None, 1, 1),
            (2, '', 'cash', '现金存入', None, 1, 1),
            (3, '__CASH__', 'cash', None, None, 1, 1),
        ],
    )
    engine = _engine_for(db)

    assert migrate_transactions_symbol_norm(engine).startswith('[OK]')
    got = dict(_rows(engine, 'SELECT id, symbol_norm FROM transactions'))
    assert got[1] == ''
    assert got[2] == ''
    assert got[3] == 'NO_VENUE:__CASH__'


def test_idempotent(tmp_path):
    """二次执行必须 `[SKIP]`：空 symbol 行不能每次都被当成「待回填」重算一遍。"""
    db = tmp_path / 'invest.db'
    _make_old_db(
        db,
        txn_rows=[
            (1, 'SZ001937', None, '兴银现金增利货币', None, 1, 1),
            (2, None, 'cash', '现金存入', None, 1, 1),
        ],
        fund_rows=[('001937', '兴银现金增利货币', 6)],
    )
    engine = _engine_for(db)

    assert migrate_transactions_symbol_norm(engine).startswith('[OK]')
    assert migrate_transactions_symbol_norm(engine).startswith('[SKIP]')
    assert migrate_transactions_symbol_norm(engine).startswith('[SKIP]')
    assert [c['name'] for c in inspect(engine).get_columns('transactions')].count('symbol_norm') == 1


def test_missing_table_skipped(tmp_path):
    """空库：表还不存在 → skip（由 create_all 按新模型建表），不得抛错阻断启动。"""
    engine = _engine_for(tmp_path / 'empty.db')
    assert migrate_transactions_symbol_norm(engine).startswith('[SKIP]')


def test_does_not_touch_symbol_literal(tmp_path):
    """`symbol` 是交易发生时的快照，只补身份列，**不改写历史字面量**。"""
    db = tmp_path / 'invest.db'
    _make_old_db(
        db,
        txn_rows=[(1, 'SZ001937', None, '兴银现金增利货币', None, 1, 1)],
        fund_rows=[('001937', '兴银现金增利货币', 6)],
    )
    engine = _engine_for(db)

    assert migrate_transactions_symbol_norm(engine).startswith('[OK]')
    assert _rows(engine, 'SELECT symbol FROM transactions') == [('SZ001937',)]


# ── PG 分支（#2689 / #2534）──────────────────────────────────────────────────
#
# 生产 user 域是 Supabase Postgres。#1677 那次事故的形态就是「迁移写成 SQLite-only，
# 本地全绿、生产两库静默不一致」，故这里钉住「不早退 + DDL 形态」。
# 数据回填走「无行」分支（PgFake 的 rows 为空），回填正确性由上面的 SQLite 用例保证。


def test_pg_branch_adds_column(monkeypatch):
    fake = PgFake({'transactions': ['id', 'symbol', 'asset_type', 'position_name', 'position_id']})
    fake.install(monkeypatch)

    result = migrate_transactions_symbol_norm(fake.engine)

    assert result.startswith('[OK]'), result
    assert 'symbol_norm' in fake.columns['transactions']
    # 加列必须带 IF NOT EXISTS（PG 语法；SQLite 不支持，故走 inspect 判存在）
    assert any('ADD COLUMN IF NOT EXISTS symbol_norm' in s for s in fake.sql), fake.sql


def test_pg_idempotent(monkeypatch):
    fake = PgFake(
        {'transactions': ['id', 'symbol', 'asset_type', 'position_name', 'position_id', 'symbol_norm']},
    )
    fake.install(monkeypatch)

    assert migrate_transactions_symbol_norm(fake.engine).startswith('[SKIP]')
    assert not any('ALTER TABLE' in s for s in fake.sql), fake.sql

# -*- coding: utf-8 -*-
"""#1662 后续 回归：positions.symbol_norm 归一身份列 + 唯一索引迁移。

验证 `migrate_positions_symbol_norm`：
- 旧库（无 symbol_norm 列）执行后补列 + 回填**正确身份** + 建唯一索引；
- 存量已有「同账户同归一身份」重复行时**显式抛错并给出修复命令**（不静默跳过、不自动合并）；
- 跨账户同码（同一基金在多个账户各持一份）是正常业务，**不得**被误判为重复；
- 幂等：重复执行不报错、不重复加列 / 建索引；
- 空库（表不存在）与非 SQLite 引擎安全 skip。

回填值的构造口径见 `app/core/symbol_utils.py::symbol_identity`，判据与
`scripts/audit_symbol_venue_conformance.py` 共用 `app/core/venues.py::venue_of_row`。
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.migrations import migrate_positions_symbol_norm

INDEX_NAME = 'uq_positions_ledger_symbol_norm'


def _make_old_db(path, rows) -> None:
    """造一个「加 symbol_norm 列之前」的 positions 表（列名取真实 schema 的子集）。

    ⚠️ `type` 是 asset_type 的**实际库列名**（ORM 里 `asset_type = Column('type', ...)`），
    不是笔误 —— 迁移 SQL 也按 `type` 取值。
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
            quantity INTEGER DEFAULT 0
        );
        """
    )
    conn.executemany(
        'INSERT INTO positions(id, symbol, type, ledger_id, family_id, quantity) VALUES (?, ?, ?, ?, ?, ?)',
        rows,
    )
    conn.commit()
    conn.close()


def _engine_for(path):
    # Windows 上 as_posix() 才与 SQLAlchemy 的 sqlite URL 约定一致（反斜杠会解析异常）
    return create_engine(f'sqlite:///{path.as_posix()}')


def _norms(engine) -> dict:
    with engine.connect() as conn:
        return dict(conn.execute(text('SELECT symbol, symbol_norm FROM positions')).fetchall())


def test_adds_column_backfills_identity_and_creates_unique_index(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(
        db,
        [
            (1, 'SZ159915', 'etf', 1, 1, 100),
            (2, '004369', 'fund', 1, 1, 200),
            (3, 'MGR_001', 'manager', 1, 1, 0),
            # 场内货基：asset_type 是货基却属交易所，回填必须判成 EXCHANGE
            (4, 'SH970164', 'money_fund', 1, 1, 300),
            # 场外货基：同码段但裸码 → OTC（与上面那条必须给出**不同**身份）
            (5, '970164', 'money_fund', 1, 1, 400),
        ],
    )
    engine = _engine_for(db)

    result = migrate_positions_symbol_norm(engine)
    assert result.startswith('[OK]')

    assert {c['name'] for c in inspect(engine).get_columns('positions')} >= {'symbol_norm'}
    assert _norms(engine) == {
        'SZ159915': 'EXCHANGE:SZ159915',
        '004369': 'OTC:004369',
        'MGR_001': 'NO_VENUE:MGR_001',
        'SH970164': 'EXCHANGE:SH970164',
        '970164': 'OTC:970164',
    }

    unique_indexes = {i['name'] for i in inspect(engine).get_indexes('positions') if i.get('unique')}
    assert INDEX_NAME in unique_indexes


def test_unique_index_actually_rejects_same_identity(tmp_path):
    """约束必须真的生效 —— 这是本卡的全部意义（不能只靠读侧查重兜住）。"""
    db = tmp_path / 'invest.db'
    _make_old_db(db, [(1, '004369', 'fund', 1, 1, 100)])
    engine = _engine_for(db)
    assert migrate_positions_symbol_norm(engine).startswith('[OK]')

    conn = sqlite3.connect(str(db))
    try:
        # 同账户、同归一身份，但**写法不同**（大小写 / 前缀）—— 字面量唯一约束挡不住，
        # 归一身份唯一索引必须挡住
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                'INSERT INTO positions(id, symbol, type, ledger_id, family_id, symbol_norm) '
                "VALUES (2, 'SZ004369', 'fund', 1, 1, 'OTC:004369')"
            )
    finally:
        conn.close()


def test_duplicate_identity_raises_with_remediation(tmp_path):
    """存量有重复身份 → 显式抛错 + 给出修复命令（不静默跳过，也不自动合并持仓）。"""
    db = tmp_path / 'invest.db'
    _make_old_db(
        db,
        [
            (10, 'SZ004369', 'fund', 20, 1, 143600),
            (20, '004369', 'fund', 20, 1, 16800),
        ],
    )
    engine = _engine_for(db)

    with pytest.raises(RuntimeError) as exc:
        migrate_positions_symbol_norm(engine)

    msg = str(exc.value)
    assert 'OTC:004369' in msg
    assert 'audit_symbol_venue_conformance.py --apply --merge' in msg
    # 抛错后不得留下半成品索引（否则下次启动会带着「约束已存在但数据仍重复」的错觉）
    assert INDEX_NAME not in {i['name'] for i in inspect(engine).get_indexes('positions')}


def test_same_code_in_different_ledgers_is_not_a_duplicate(tmp_path):
    """跨账户同码是**正常业务**（同一只基金在多个账户各持一份），绝不能合并。"""
    db = tmp_path / 'invest.db'
    _make_old_db(
        db,
        [
            (1, '004369', 'fund', 20, 1, 100),
            (2, '004369', 'fund', 21, 1, 200),
        ],
    )
    engine = _engine_for(db)

    assert migrate_positions_symbol_norm(engine).startswith('[OK]')
    assert INDEX_NAME in {i['name'] for i in inspect(engine).get_indexes('positions')}


def test_null_ledger_id_rows_are_not_treated_as_duplicates(tmp_path):
    """`ledger_id IS NULL` 的行不参与唯一约束（SQLite 视 NULL 互不相等，与旧的字面量约束同语义）。

    回归点：`GROUP BY` 会把 NULL 归到同一组，若不显式排除就会**误报**重复、无谓阻断启动。
    """
    db = tmp_path / 'invest.db'
    _make_old_db(
        db,
        [
            (1, '004369', 'fund', None, 1, 100),
            (2, '004369', 'fund', None, 1, 200),
        ],
    )
    engine = _engine_for(db)

    assert migrate_positions_symbol_norm(engine).startswith('[OK]')
    assert INDEX_NAME in {i['name'] for i in inspect(engine).get_indexes('positions')}


def test_idempotent(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db, [(1, '004369', 'fund', 1, 1, 100)])
    engine = _engine_for(db)

    assert migrate_positions_symbol_norm(engine).startswith('[OK]')
    second = migrate_positions_symbol_norm(engine)
    assert second.startswith('[SKIP]')

    cols = [c['name'] for c in inspect(engine).get_columns('positions')]
    assert cols.count('symbol_norm') == 1  # 未重复加列


def test_missing_table_skipped(tmp_path):
    """空库：表还不存在 → skip（由 create_all 按新模型建表），不得抛错阻断启动。"""
    engine = _engine_for(tmp_path / 'empty.db')
    assert migrate_positions_symbol_norm(engine).startswith('[SKIP]')


class _FakeEngine:
    """只需 url 属性的假引擎：非 SQLite 分支在读 url 后即返回，不会真正连库。"""

    def __init__(self, url: str):
        self.url = url


def test_non_sqlite_skipped():
    assert migrate_positions_symbol_norm(_FakeEngine('postgresql://u:p@host/db')).startswith('[SKIP]')
    assert migrate_positions_symbol_norm(_FakeEngine('mysql+pymysql://u:p@host/db')).startswith('[SKIP]')

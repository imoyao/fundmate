# -*- coding: utf-8 -*-
"""#3246 回归：`ledgers` 可见性两列的迁移.

`migrate_ledger_visibility` 的关键契约只有一条，但它最容易写错：

**存量行必须变成 `shared`，不能是 `private`。**

本机现状是 16 个账户、4 个同家庭账号。若 DDL 直接给 `DEFAULT 'private'`，升级后四个
账号彼此看不见账户——用户的第一反应是「数据丢了」。所以加列时**不带默认值**，再由
`UPDATE ... WHERE visibility IS NULL` 回填 `shared`；新行才是 `private`（由 ORM default）。

其余用例覆盖：幂等（不把用户后来改回的 private 再翻成 shared）、空库 skip、
PG 分支不早退且发 `ADD COLUMN IF NOT EXISTS`（#2534）。
"""

import sqlite3

from sqlalchemy import create_engine, inspect, text

from app.core.migrations_ledgers import migrate_ledger_visibility

from .migrations_pg_fake import PgFake


def _make_old_db(path) -> None:
    """造一个「加可见性列之前」的 ledgers 表（只有 id/name/family_id）."""
    conn = sqlite3.connect(str(path))
    conn.execute('CREATE TABLE ledgers (id INTEGER PRIMARY KEY, name VARCHAR(100), family_id INTEGER)')
    conn.executemany(
        'INSERT INTO ledgers(id, name, family_id) VALUES (?, ?, ?)',
        [(1, '华泰证券', 1), (2, '家庭现金', 1), (3, '别家账户', 2)],
    )
    conn.commit()
    conn.close()


def _engine_for(path):
    # Windows 上 as_posix() 才与 SQLAlchemy 的 sqlite URL 约定一致（反斜杠会解析异常）
    return create_engine(f'sqlite:///{path.as_posix()}')


def test_adds_columns_and_backfills_existing_rows_as_shared(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    result = migrate_ledger_visibility(engine)
    assert result.startswith('[OK]'), result

    cols = {c['name'] for c in inspect(engine).get_columns('ledgers')}
    assert {'visibility', 'owner_user_id'} <= cols

    with engine.connect() as conn:
        rows = conn.execute(text('SELECT id, visibility, owner_user_id FROM ledgers ORDER BY id')).fetchall()

    assert [r[1] for r in rows] == ['shared', 'shared', 'shared']  # 存量行不是 private
    assert [r[2] for r in rows] == [None, None, None]  # shared 不需要判定主体


def test_does_not_flip_user_changed_private_back_to_shared(tmp_path):
    """幂等方向：回填只补 NULL，不覆盖已有值（否则用户设的 private 每次启动被翻回 shared）."""
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    migrate_ledger_visibility(engine)
    with engine.connect() as conn:
        conn.execute(text("UPDATE ledgers SET visibility = 'private', owner_user_id = 11 WHERE id = 1"))
        conn.commit()

    second = migrate_ledger_visibility(engine)
    assert second.startswith('[SKIP]'), second

    with engine.connect() as conn:
        value = conn.execute(text('SELECT visibility FROM ledgers WHERE id = 1')).scalar()
    assert value == 'private'


def test_idempotent_does_not_add_columns_twice(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    assert migrate_ledger_visibility(engine).startswith('[OK]')
    assert migrate_ledger_visibility(engine).startswith('[SKIP]')

    cols = [c['name'] for c in inspect(engine).get_columns('ledgers')]
    assert cols.count('visibility') == 1
    assert cols.count('owner_user_id') == 1


def test_missing_table_skipped(tmp_path):
    """空库：表还不存在 → skip（由 create_all 按新模型建表），不得抛错阻断启动."""
    engine = _engine_for(tmp_path / 'empty.db')
    assert migrate_ledger_visibility(engine).startswith('[SKIP]')


def test_pg_branch_adds_columns_with_if_not_exists(monkeypatch):
    """#2534：PG 不早退，且发 `ADD COLUMN IF NOT EXISTS`（幂等语法，钉死文本）."""
    fake = PgFake({'ledgers': ['id', 'name', 'family_id']})
    fake.install(monkeypatch)

    result = migrate_ledger_visibility(fake.engine)

    assert result.startswith('[OK]'), f'PG 分支不许再返回跳过：{result}'
    assert any('ADD COLUMN IF NOT EXISTS visibility VARCHAR(10)' in s for s in fake.sql), fake.sql
    assert any('ADD COLUMN IF NOT EXISTS owner_user_id INTEGER' in s for s in fake.sql), fake.sql
    assert any(s.lstrip().upper().startswith('UPDATE LEDGERS') for s in fake.sql)


def test_pg_branch_missing_table_skips(monkeypatch):
    fake = PgFake({})
    fake.install(monkeypatch)

    assert migrate_ledger_visibility(fake.engine).startswith('[SKIP]')

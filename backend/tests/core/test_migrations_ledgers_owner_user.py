# -*- coding: utf-8 -*-
"""#1173 回归：ledgers 归属成员列迁移（`migrate_ledgers_owner_user`）。

钉住四件事：

1. SQLite 旧结构库：补 `owner_user_id` 列 + 建索引，**存量行一条不丢**、新列留 NULL；
2. 幂等：重复执行不报错、不重复加列/建索引；
3. 表不存在（空库）安全 skip；
4. PG 分支**不早退**（本仓没有 Alembic、`create_all()` 不给存量表加列，
   漏掉 PG 侧 = 生产 Supabase 上 `_validate_schema` 判缺列 → 拒绝启动，#2469/#2532 同因）。

本地没有 PG 可连，PG 分支只能钉 **SQL 形态**（发的是 `ADD COLUMN IF NOT EXISTS`
与 `CREATE INDEX IF NOT EXISTS`）；DDL 被静默忽略时迁移必须显性抛错。
"""

import re
import sqlite3

import pytest
import sqlalchemy
from sqlalchemy import create_engine, inspect

import app.core.migrations as migrations_mod
from app.core.migrations import migrate_ledgers_owner_user

INDEX_NAME = 'ix_ledgers_owner_user_id'


def _make_old_db(path) -> None:
    """造一个「补列之前」的 ledgers 结构（贴近生产上缺 owner_user_id 的旧表）。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE ledgers (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            ledger_type VARCHAR(20),
            family_id INTEGER NOT NULL DEFAULT 1
        );
        INSERT INTO ledgers (id, name, ledger_type, family_id) VALUES (1, '招行', 'bank', 1);
        INSERT INTO ledgers (id, name, ledger_type, family_id) VALUES (2, '华泰', 'stock', 1);
        """
    )
    conn.commit()
    conn.close()


def _columns(engine, table='ledgers') -> set:
    return {c['name'] for c in inspect(engine).get_columns(table)}


def test_adds_column_and_index_keeps_rows(tmp_path):
    """SQLite 旧结构库：列与索引补齐；存量行一条不丢；新列 NULL（不猜归属）。"""
    db = tmp_path / 'old.db'
    _make_old_db(db)
    engine = create_engine(f'sqlite:///{db}')

    result = migrate_ledgers_owner_user(engine)

    assert result.startswith('[OK]')
    assert 'owner_user_id' in _columns(engine)
    with engine.connect() as conn:
        rows = conn.execute(sqlalchemy.text('SELECT id, name, owner_user_id FROM ledgers ORDER BY id')).fetchall()
        indexes = conn.execute(sqlalchemy.text("SELECT name FROM sqlite_master WHERE type='index'")).fetchall()
    assert [r[0] for r in rows] == [1, 2], '迁移不许丢行'
    assert [r[2] for r in rows] == [None, None], '只加列不回填：归属必须留 NULL（未指定）'
    assert INDEX_NAME in {r[0] for r in indexes}


def test_idempotent(tmp_path):
    """重复执行：不报错，第二次明确报「已存在」。"""
    db = tmp_path / 'old.db'
    _make_old_db(db)
    engine = create_engine(f'sqlite:///{db}')

    first = migrate_ledgers_owner_user(engine)
    second = migrate_ledgers_owner_user(engine)

    assert first.startswith('[OK]')
    assert second.startswith('[SKIP]') and '已存在' in second
    assert 'owner_user_id' in _columns(engine)


def test_missing_table_skipped(tmp_path):
    """空库（表还没建）：安全 skip，不抛错——init_db 随后按新模型建表。"""
    engine = create_engine(f'sqlite:///{tmp_path / "empty.db"}')

    result = migrate_ledgers_owner_user(engine)

    assert result.startswith('[SKIP]') and 'ledgers' in result


# ---------------------------------------------------------------------------
# PG 分支：本地无 PG，用假 engine + 假 inspector 钉住 SQL 形态与「不再早退」
# ---------------------------------------------------------------------------


class _PgFake:
    """模拟 PG 引擎：记录发出的 SQL；``apply_ddl=False`` 时模拟「DDL 被静默忽略」。"""

    def __init__(self, apply_ddl=True):
        self.cols = ['id', 'name', 'ledger_type', 'family_id']
        self.indexes = []
        self.sql = []
        self.apply_ddl = apply_ddl

    def make_engine(self):
        fake = self

        class _Conn:
            def execute(self, stmt):
                sql = str(stmt)
                fake.sql.append(sql)
                if not fake.apply_ddl:
                    return
                m = re.search(r'ADD COLUMN (?:IF NOT EXISTS )?(\w+)', sql)
                if m:
                    fake.cols.append(m.group(1))
                m = re.search(r'CREATE INDEX IF NOT EXISTS (\w+)', sql)
                if m:
                    fake.indexes.append(m.group(1))

            def commit(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class _Engine:
            url = 'postgresql+psycopg://user:pass@127.0.0.1:1/db'

            def connect(self):
                return _Conn()

        return _Engine()

    def make_inspector(self):
        fake = self

        class _Inspector:
            def get_table_names(self):
                return ['ledgers']

            def get_columns(self, table):
                assert table == 'ledgers'
                return [{'name': c} for c in fake.cols]

            def get_indexes(self, table):
                assert table == 'ledgers'
                return [{'name': i} for i in fake.indexes]

        return lambda engine: _Inspector()


def test_pg_branch_adds_column_with_if_not_exists(monkeypatch):
    """PG 分支：不早退，发 `ADD COLUMN IF NOT EXISTS` + 幂等建索引。"""
    fake = _PgFake()
    monkeypatch.setattr(migrations_mod, 'inspect', fake.make_inspector())

    result = migrate_ledgers_owner_user(fake.make_engine())

    assert result.startswith('[OK]'), f'PG 分支不许返回跳过：{result}'
    assert 'owner_user_id' in fake.cols
    assert any(
        re.fullmatch(r'ALTER TABLE ledgers ADD COLUMN IF NOT EXISTS owner_user_id INTEGER', sql) for sql in fake.sql
    ), f'加列 DDL 形态不对：{fake.sql}'
    assert INDEX_NAME in fake.indexes, f'索引没建：{fake.sql}'


def test_pg_branch_skips_existing_column(monkeypatch):
    """PG 上列与索引已齐（重复执行）：不发 DDL，返回已存在。"""
    fake = _PgFake()
    fake.cols.append('owner_user_id')
    fake.indexes.append(INDEX_NAME)
    monkeypatch.setattr(migrations_mod, 'inspect', fake.make_inspector())

    result = migrate_ledgers_owner_user(fake.make_engine())

    assert result.startswith('[SKIP]') and '已存在' in result
    assert fake.sql == [], f'结构已齐时不该发 DDL：{fake.sql}'


def test_raises_when_column_still_missing(monkeypatch):
    """收尾自校验：DDL 没生效（列仍缺）必须抛错，而不是返回「看起来 OK」。"""
    fake = _PgFake(apply_ddl=False)
    monkeypatch.setattr(migrations_mod, 'inspect', fake.make_inspector())

    with pytest.raises(RuntimeError) as exc:
        migrate_ledgers_owner_user(fake.make_engine())

    assert '仍缺列' in str(exc.value)
    assert 'Postgres' in str(exc.value)

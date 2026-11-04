# -*- coding: utf-8 -*-
"""#2532 回归：transactions 费用拆分四列迁移（`migrate_transaction_fee_breakdown`）必须覆盖 Postgres。

## 为什么需要这份回归网

该迁移第一版写着「非 SQLite 引擎由 ORM 模型 / 迁移工具负责，直接跳过」。那前提在本仓
**不成立**：

- 本仓没有 Alembic，迁移都是 `app/core/migrations.py` 里手写的函数；
- `create_all()` 只建缺失的表，**不会给已有表加列**；
- 生产 user 域是 Supabase Postgres（手工建表）。

⇒ 四列在生产永远加不上，`init_db()` 的 `_validate_schema` 判定「表 transactions 缺列」
并**拒绝启动**（schedule 运行 39848022855 实测），每日调度整条链路停摆。

本文件钉住四件事（本地没有 PG 可连，PG 分支只能钉 **SQL 形态**，否则语法错要等生产才发现）：

1. PG 分支**不再早退**，且发出 `ADD COLUMN IF NOT EXISTS`；
2. SQLite 旧结构库补列后**列齐、存量行一条不丢、新列留 NULL**；
3. **幂等**：重复执行不报错、不重复加列；
4. 表不存在（空库）安全 skip，且**加列失败必须显性抛错**（不留「看起来 OK」的半截状态）。
"""

import re
import sqlite3

import pytest
import sqlalchemy
from sqlalchemy import create_engine, inspect

import app.core.migrations as migrations_mod
from app.core.migrations import migrate_transaction_fee_breakdown

FEE_COLUMNS = ('commission', 'stamp_duty', 'transfer_fee', 'other_fee')


def _make_old_db(path) -> None:
    """造一个「补列之前」的 transactions 结构（贴近生产上缺四列的旧表）。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            symbol VARCHAR(30) NOT NULL,
            fee INTEGER
        );
        INSERT INTO transactions (id, symbol, fee) VALUES (1, '000001', 1500);
        INSERT INTO transactions (id, symbol, fee) VALUES (2, '600519', 0);
        """
    )
    conn.commit()
    conn.close()


def _columns(engine, table='transactions') -> set:
    return {c['name'] for c in inspect(engine).get_columns(table)}


def test_adds_four_columns_and_keeps_rows(tmp_path):
    """SQLite 旧结构库：四列补齐；存量行一条不丢；新列全 NULL（不造数）。"""
    db = tmp_path / 'old.db'
    _make_old_db(db)
    engine = create_engine(f'sqlite:///{db}')

    result = migrate_transaction_fee_breakdown(engine)

    assert result.startswith('[OK]')
    assert set(FEE_COLUMNS) <= _columns(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            sqlalchemy.text(
                'SELECT id, symbol, fee, commission, stamp_duty, transfer_fee, other_fee FROM transactions ORDER BY id'
            )
        ).fetchall()
    assert [r[0] for r in rows] == [1, 2], '迁移不许丢行'
    assert rows[0][2] == 1500, '聚合 fee 必须原样保留'
    assert rows[0][3:] == (None, None, None, None), '只加列不回填：新列必须留 NULL'


def test_idempotent(tmp_path):
    """重复执行：不报错、不重复加列，第二次明确报「已存在」。"""
    db = tmp_path / 'old.db'
    _make_old_db(db)
    engine = create_engine(f'sqlite:///{db}')

    first = migrate_transaction_fee_breakdown(engine)
    second = migrate_transaction_fee_breakdown(engine)

    assert first.startswith('[OK]')
    assert second.startswith('[SKIP]') and '已存在' in second
    assert set(FEE_COLUMNS) <= _columns(engine)


def test_missing_table_skipped(tmp_path):
    """空库（表还没建）：安全 skip，不抛错——init_db 随后按新模型建表。"""
    engine = create_engine(f'sqlite:///{tmp_path / "empty.db"}')

    result = migrate_transaction_fee_breakdown(engine)

    assert result.startswith('[SKIP]') and 'transactions 表不存在' in result


# ---------------------------------------------------------------------------
# PG 分支：本地无 PG，用假 engine + 假 inspector 钉住 SQL 形态与「不再早退」
# ---------------------------------------------------------------------------


class _PgFake:
    """模拟 PG 引擎：记录发出的 SQL；``apply_ddl=False`` 时模拟「DDL 被静默忽略」。"""

    def __init__(self, apply_ddl=True):
        self.cols = ['id', 'symbol', 'fee']
        self.sql = []
        self.apply_ddl = apply_ddl

    def make_engine(self):
        fake = self

        class _Conn:
            def execute(self, stmt):
                sql = str(stmt)
                fake.sql.append(sql)
                m = re.search(r'ADD COLUMN (?:IF NOT EXISTS )?(\w+)', sql)
                if m and fake.apply_ddl:
                    fake.cols.append(m.group(1))

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
                return ['transactions']

            def get_columns(self, table):
                assert table == 'transactions'
                return [{'name': c} for c in fake.cols]

        return lambda engine: _Inspector()


def test_pg_branch_adds_columns_with_if_not_exists(monkeypatch):
    """PG 分支：不再早退，四列各发一条 `ADD COLUMN IF NOT EXISTS`（幂等语法）。"""
    fake = _PgFake()
    monkeypatch.setattr(migrations_mod, 'inspect', fake.make_inspector())

    result = migrate_transaction_fee_breakdown(fake.make_engine())

    assert result.startswith('[OK]'), f'PG 分支不许再返回跳过：{result}'
    assert '非 SQLite' not in result
    assert set(FEE_COLUMNS) <= set(fake.cols)
    assert len(fake.sql) == 4, f'应发 4 条 DDL，实际：{fake.sql}'
    for name in FEE_COLUMNS:
        assert any(
            re.fullmatch(rf'ALTER TABLE transactions ADD COLUMN IF NOT EXISTS {name} INTEGER', sql) for sql in fake.sql
        ), f'{name} 的 DDL 形态不对：{fake.sql}'


def test_pg_branch_skips_existing_columns(monkeypatch):
    """PG 上列已齐（重复执行）：不发任何 DDL，返回已存在。"""
    fake = _PgFake()
    fake.cols.extend(FEE_COLUMNS)
    monkeypatch.setattr(migrations_mod, 'inspect', fake.make_inspector())

    result = migrate_transaction_fee_breakdown(fake.make_engine())

    assert result.startswith('[SKIP]') and '已存在' in result
    assert fake.sql == [], f'列已齐时不该发 DDL：{fake.sql}'


def test_raises_when_columns_still_missing(monkeypatch):
    """收尾自校验：DDL 没生效（列仍缺）必须抛错，而不是返回「看起来 OK」的字符串。"""
    fake = _PgFake(apply_ddl=False)
    monkeypatch.setattr(migrations_mod, 'inspect', fake.make_inspector())

    with pytest.raises(RuntimeError) as exc:
        migrate_transaction_fee_breakdown(fake.make_engine())

    assert '仍缺列' in str(exc.value)
    assert 'Postgres' in str(exc.value)

# -*- coding: utf-8 -*-
"""#2469 回归：user 域 watchlist 三表补列迁移（`migrate_watchlist_user_domain_columns`）。

生产 user 域（Supabase Postgres）上的 watchlist 表是**旧结构**：
``watchlist_groups`` 缺 ``sort_order`` / ``is_visible`` / ``entity_type`` / ``family_id``，
``watchlist_item_tags`` 缺 ``id``（自增主键）。于是 ``_validate_schema`` 判
「库结构与模型不一致」并**拒绝启动** → 每日调度（#1490）全线停摆。

本文件钉住：
- 旧库（缺列 + 缺 id）执行后**列补齐、存量行一条不少**（迁移不许丢数据）；
- **幂等**：重复执行不报错、不重复加列；
- 空库（表不存在）安全 skip；
- PG 分支的 SQL 形态（``IF NOT EXISTS`` / ``SERIAL``）——本地没有 PG，
  只能靠 SQL 生成被钉住，否则 PG 侧一旦写错语法，**在生产才发现**。
"""

import sqlite3

import pytest
import sqlalchemy
from sqlalchemy import create_engine, inspect, text

from app.core.migrations import (
    _add_column_sql,
    _add_id_serial_sql,
    migrate_watchlist_user_domain_columns,
)


def _make_old_db(path) -> None:
    """造一个「补列之前」的 user 域 watchlist 结构（贴近生产 Supabase 上的形状）。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE watchlist (
            id INTEGER PRIMARY KEY,
            symbol VARCHAR(30) NOT NULL
        );
        CREATE TABLE watchlist_tag_defs (
            id INTEGER PRIMARY KEY,
            name VARCHAR(50) NOT NULL
        );
        CREATE TABLE watchlist_groups (
            id INTEGER NOT NULL,
            name VARCHAR(50) NOT NULL,
            color VARCHAR(7),
            is_system BOOLEAN,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id)
        );
        INSERT INTO watchlist_groups (id, name, color, is_system)
        VALUES (1, '核心持仓', '#ff0000', 0);
        CREATE TABLE watchlist_item_tags (
            item_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            CONSTRAINT uk_item_tag UNIQUE (item_id, tag_id),
            FOREIGN KEY(item_id) REFERENCES watchlist (id) ON DELETE CASCADE,
            FOREIGN KEY(tag_id) REFERENCES watchlist_tag_defs (id) ON DELETE CASCADE
        );
        INSERT INTO watchlist_item_tags (item_id, tag_id) VALUES (1, 1), (1, 2);
        """
    )
    conn.commit()
    conn.close()


def _engine_for(path):
    # Windows 上 as_posix() 才与 SQLAlchemy 的 sqlite URL 约定一致（反斜杠会解析异常）
    return create_engine(f'sqlite:///{path.as_posix()}')


def test_adds_missing_columns_and_keeps_rows(tmp_path):
    """旧库补列后：列齐、行不丢、id 唯一非空。"""
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    result = migrate_watchlist_user_domain_columns(engine)
    assert result.startswith('[OK]'), result

    cols = {c['name'] for c in inspect(engine).get_columns('watchlist_groups')}
    for name in ('sort_order', 'is_visible', 'entity_type', 'family_id'):
        assert name in cols, f'缺列 {name}'

    with engine.connect() as conn:
        rows = conn.execute(text('SELECT id, name, family_id FROM watchlist_groups')).fetchall()
        assert len(rows) == 1, '存量行被迁移弄丢了'
        assert rows[0][1] == '核心持仓'
        assert rows[0][2] == 1, 'family_id 应按默认值 1 收编（默认家庭）'

        tags = conn.execute(text('SELECT id, item_id, tag_id FROM watchlist_item_tags')).fetchall()
        assert len(tags) == 2, '存量行被迁移弄丢了'
        ids = [t[0] for t in tags]
        assert all(i is not None for i in ids), 'id 不得为空'
        assert len(set(ids)) == 2, 'id 必须唯一'
        assert sorted((t[1], t[2]) for t in tags) == [(1, 1), (1, 2)], '原有关联关系被改动了'


def test_unique_constraint_survives_rebuild(tmp_path):
    """重建后 (item_id, tag_id) 唯一约束仍在（否则会产生重复关联行）。"""
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)
    migrate_watchlist_user_domain_columns(engine)

    with engine.connect() as conn:
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            conn.execute(text('INSERT INTO watchlist_item_tags (id, item_id, tag_id) VALUES (99, 1, 1)'))
            conn.commit()


def test_is_idempotent(tmp_path):
    """重复执行不报错、不重复加列、id 不变。"""
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    migrate_watchlist_user_domain_columns(engine)
    with engine.connect() as conn:
        first = conn.execute(text('SELECT id, item_id FROM watchlist_item_tags ORDER BY id')).fetchall()
    migrate_watchlist_user_domain_columns(engine)
    with engine.connect() as conn:
        second = conn.execute(text('SELECT id, item_id FROM watchlist_item_tags ORDER BY id')).fetchall()

    assert first == second, '重复执行改动了数据'


def test_empty_db_is_skipped(tmp_path):
    """空库（表不存在）安全 skip，交给 create_all 建表。"""
    db = tmp_path / 'empty.db'
    engine = _engine_for(db)
    result = migrate_watchlist_user_domain_columns(engine)
    assert '不存在' in result or result.startswith('[OK]')


def test_family_id_index_created(tmp_path):
    """family_id 的索引要建出来（模型声明 index=True）。"""
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)
    migrate_watchlist_user_domain_columns(engine)
    idx = {i['name'] for i in inspect(engine).get_indexes('watchlist_groups')}
    assert 'ix_watchlist_groups_family_id' in idx, idx


def test_self_check_raises_when_columns_not_added(tmp_path, monkeypatch):
    """迁移**没真正补上列**时必须抛错（不留半截状态、静默放过）。

    做法：把加列 SQL 换成无害语句 ⇒ 列没加上 ⇒ 收尾自校验必须发现并抛错。
    没有这条，收尾自校验就只是个「看起来在检查」的摆设。
    """
    import app.core.migrations as mig

    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)
    monkeypatch.setattr(mig, '_add_column_sql', lambda *a, **k: 'SELECT 1')

    with pytest.raises(RuntimeError):
        mig.migrate_watchlist_user_domain_columns(engine)


def test_self_check_raises_when_id_not_added(tmp_path, monkeypatch):
    """id 没补上时同样必须抛错（重建路径被换掉的情形）。"""
    import app.core.migrations as mig

    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)
    monkeypatch.setattr(mig, '_sqlite_rebuild_watchlist_item_tags', lambda eng: '[SKIP] 被替换')

    with pytest.raises(RuntimeError):
        mig.migrate_watchlist_user_domain_columns(engine)


def test_postgres_sql_uses_if_not_exists_and_serial():
    """PG 分支的 SQL 形态被钉住（本地无 PG，写错只能在生产暴露）。"""
    pg_col = _add_column_sql('watchlist_groups', 'family_id', 'INTEGER NOT NULL DEFAULT 1', True)
    assert pg_col == 'ALTER TABLE watchlist_groups ADD COLUMN IF NOT EXISTS family_id INTEGER NOT NULL DEFAULT 1'

    sqlite_col = _add_column_sql('watchlist_groups', 'family_id', 'INTEGER NOT NULL DEFAULT 1', False)
    assert 'IF NOT EXISTS' not in sqlite_col, 'SQLite 不支持 ADD COLUMN IF NOT EXISTS'

    pg_id = _add_id_serial_sql('watchlist_item_tags', True)
    assert 'SERIAL' in pg_id and 'IF NOT EXISTS' in pg_id, pg_id

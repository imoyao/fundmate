# -*- coding: utf-8 -*-
"""组合名唯一迁移：存量重名去冲突 + 部分唯一索引。

为什么要有这层（而不是只靠视图里的 409）：组合是**软删除**的，普通唯一索引会让
「删掉的名字永远建不回来」；而只有应用层校验时，任何旁路写入（导入脚本、手工 SQL、
两个并发请求）都能再造出同名组合。故索引是部分唯一索引（只约束未删除行），
键与应用层同口径 ``lower(trim(name))``。

存量重名必须能被迁移自动收拾：用户升级到这一版时库里很可能已经有两个「养老计划」，
若迁移 fail closed，应用启动即失败，用户连进页面改名的机会都没有。
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.migrations import migrate_portfolios_unique_name


def _make_legacy_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE portfolios(
            id INTEGER PRIMARY KEY,
            family_id INTEGER NOT NULL DEFAULT 1,
            name VARCHAR(100) NOT NULL,
            is_deleted BOOLEAN DEFAULT 0
        );
        -- 1 / 2：完全同名（本次要修的历史数据）
        INSERT INTO portfolios VALUES (1, 1, '养老计划', 0);
        INSERT INTO portfolios VALUES (2, 1, '养老计划', 0);
        -- 3/4/5：大小写 + 空白变体，人眼里同名（4 号还带内部双空格与首尾空格）
        INSERT INTO portfolios VALUES (3, 1, 'Retire 2026', 0);
        INSERT INTO portfolios VALUES (4, 1, '  RETIRE   2026 ', 0);
        INSERT INTO portfolios VALUES (5, 1, 'retire 2026', 0);
        -- 6：已软删除 —— 不进索引，同名可被重新使用
        INSERT INTO portfolios VALUES (6, 1, '旧组合', 1);
        -- 8：另一个家庭，同名合法
        INSERT INTO portfolios VALUES (8, 2, '养老计划', 0);
        """
    )
    conn.commit()
    conn.close()


def test_migration_renames_duplicates_and_keeps_earliest(tmp_path):
    db_path = tmp_path / 'legacy.db'
    _make_legacy_db(str(db_path))
    engine = create_engine(f'sqlite:///{db_path}')

    result = migrate_portfolios_unique_name(engine)
    assert '已重建' in result
    # 1 条空白归一（id=4）+ 3 条重名改名（id=2/4/5）
    assert '存量规整 1 条' in result
    assert '重名改名 3 条' in result

    with engine.connect() as conn:
        rows = dict(conn.execute(text('SELECT id, name FROM portfolios')).fetchall())
    # 最早的一条原样保留
    assert rows[1] == '养老计划'
    assert rows[3] == 'Retire 2026'
    # 后建的加序号
    assert rows[2] == '养老计划（2）'
    # 4 号先被空白归一（内部双空格 → 单空格），再因与 3 号同键被改名
    assert rows[4] == 'RETIRE 2026（2）'
    # 5 号跳过（2）直接到（3）：4 号已占掉「retire 2026（2）」这个键（大小写不敏感）
    assert rows[5] == 'retire 2026（3）'
    # 软删除那条不动
    assert rows[6] == '旧组合'


def test_migration_creates_partial_unique_index(tmp_path):
    db_path = tmp_path / 'legacy.db'
    _make_legacy_db(str(db_path))
    engine = create_engine(f'sqlite:///{db_path}')

    migrate_portfolios_unique_name(engine)

    names = {i['name'] for i in inspect(engine).get_indexes('portfolios')}
    # 表达式索引在 SQLite 侧反射不出来（见 _index_exists docstring），故查 sqlite_master
    with engine.connect() as conn:
        found = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND name='uq_portfolios_family_name_alive'")
        ).scalar()
    assert found == 'uq_portfolios_family_name_alive'
    assert 'uq_portfolios_family_name_alive' not in names  # 记录反射确实看不见它


def test_index_blocks_duplicate_but_allows_reuse_after_soft_delete(tmp_path):
    db_path = tmp_path / 'legacy.db'
    _make_legacy_db(str(db_path))
    engine = create_engine(f'sqlite:///{db_path}')
    migrate_portfolios_unique_name(engine)

    with pytest.raises(IntegrityError):
        with engine.connect() as conn:
            # 大小写 + 空白变体同样被索引挡住（键是 lower(trim(name))）
            conn.execute(
                text("INSERT INTO portfolios(id, family_id, name, is_deleted) VALUES (99, 1, ' 养老计划 ', 0)")
            )
            conn.commit()

    with engine.connect() as conn:
        # 软删除行不进索引：同一个名字可以再建一条未删除的
        conn.execute(text("INSERT INTO portfolios(id, family_id, name, is_deleted) VALUES (100, 1, '旧组合', 0)"))
        conn.commit()
        # 其它家庭同名也允许
        conn.execute(text("INSERT INTO portfolios(id, family_id, name, is_deleted) VALUES (101, 3, '养老计划', 0)"))
        conn.commit()


def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / 'legacy.db'
    _make_legacy_db(str(db_path))
    engine = create_engine(f'sqlite:///{db_path}')

    migrate_portfolios_unique_name(engine)
    with engine.connect() as conn:
        after_first = dict(conn.execute(text('SELECT id, name FROM portfolios')).fetchall())

    second = migrate_portfolios_unique_name(engine)
    with engine.connect() as conn:
        after_second = dict(conn.execute(text('SELECT id, name FROM portfolios')).fetchall())

    assert after_first == after_second
    assert '已存在' in second


def test_migration_skips_missing_table(tmp_path):
    """空库：init_db 的 create_all 会按新模型建表，迁移不该凭空造表"""
    engine = create_engine(f'sqlite:///{tmp_path / "empty.db"}')
    assert migrate_portfolios_unique_name(engine).startswith('[SKIP]')

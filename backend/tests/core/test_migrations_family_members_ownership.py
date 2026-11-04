# -*- coding: utf-8 -*-
"""#1173 回归：家庭成员档案建表 + 账户归属列补列迁移。

本文件钉住：

- **建表 + 加列都真的发生**：迁移跑完 ``family_members`` 表在、``ledgers.owner_member_id`` 列在；
- **幂等**：重复执行不报错、不重复加列（生产启动路径会反复跑迁移）；
- **存量行一条不少**：迁移只加列不回填，老账户全部保留（``owner_member_id`` 留 NULL
  = 未归属/家庭共有，**回填等于编造归属**）；
- 空库（``ledgers`` 表不存在）安全 skip；
- **PG 分支的 SQL 形态**：本地没有 PG，只能靠 SQL 生成被钉住——否则 PG 侧一旦写错语法，
  **在生产才发现**（#2469 / #2532 两次生产停摆同此根因）。
"""

import sqlite3

import pytest
import sqlalchemy
from sqlalchemy import create_engine, inspect, text

from app.core.migrations import _add_column_sql, _is_postgres, migrate_family_members_ownership

from .migrations_pg_fake import PgFake


def _make_old_db(path) -> None:
    """造一个「补列之前」的 user 域结构：ledgers 无 owner_member_id，无 family_members 表。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE ledgers (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            family_id INTEGER DEFAULT 1
        );
        INSERT INTO ledgers (name, family_id) VALUES ('招行', 1);
        INSERT INTO ledgers (name, family_id) VALUES ('老婆的招行', 1);
        """
    )
    conn.commit()
    conn.close()


@pytest.fixture
def old_db(tmp_path):
    path = tmp_path / 'old_user.db'
    _make_old_db(path)
    engine = create_engine(f'sqlite:///{path}')
    yield engine
    engine.dispose()


def test_migration_creates_table_and_column(old_db):
    """迁移跑完：family_members 表在、ledgers.owner_member_id 列在。"""
    result = migrate_family_members_ownership(old_db)
    assert result.startswith('[OK]')

    names = set(inspect(old_db).get_table_names())
    assert 'family_members' in names

    cols = {c['name'] for c in inspect(old_db).get_columns('ledgers')}
    assert 'owner_member_id' in cols


def test_migration_is_idempotent(old_db):
    """幂等：重复跑不报错、不重复加列（生产启动路径反复跑迁移）。"""
    migrate_family_members_ownership(old_db)
    second = migrate_family_members_ownership(old_db)
    assert second.startswith('[OK]')
    assert '已存在' in second

    cols = [c['name'] for c in inspect(old_db).get_columns('ledgers')]
    assert cols.count('owner_member_id') == 1


def test_migration_preserves_existing_rows(old_db):
    """存量账户一条不少，且归属留 NULL（不回填 = 不编造归属）。"""
    migrate_family_members_ownership(old_db)
    with old_db.connect() as conn:
        rows = conn.execute(text('SELECT name, owner_member_id FROM ledgers ORDER BY id')).all()
    assert [r[0] for r in rows] == ['招行', '老婆的招行']
    assert all(r[1] is None for r in rows)


def test_migration_creates_indexes(old_db):
    """索引建上（owner_member_id 是筛选热路径）。"""
    migrate_family_members_ownership(old_db)
    with old_db.connect() as conn:
        conn.execute(text('CREATE TABLE IF NOT EXISTS ix_probe (id INTEGER)'))
        conn.commit()
    idx = {i['name'] for i in inspect(old_db).get_indexes('family_members')}
    assert 'ix_family_members_family_id' in idx


def test_migration_skips_when_ledgers_missing(tmp_path):
    """空库（ledgers 表不存在）安全 skip——create_all 会按新模型建表。"""
    engine = create_engine(f'sqlite:///{tmp_path / "empty.db"}')
    result = migrate_family_members_ownership(engine)
    assert result.startswith('[SKIP]')
    engine.dispose()


def test_pg_branch_uses_if_not_exists():
    """PG 分支用 ``ADD COLUMN IF NOT EXISTS``（并发友好）；SQLite 不支持该语法故不加。

    生产 user 域就是 Postgres——这条 SQL 写错会在生产才发现。
    """
    assert 'IF NOT EXISTS' in _add_column_sql('ledgers', 'owner_member_id', 'INTEGER', True)
    assert 'IF NOT EXISTS' not in _add_column_sql('ledgers', 'owner_member_id', 'INTEGER', False)


def test_is_postgres_detects_pg_url():
    """PG URL 识别——迁移的方言分支全靠它（用 PgFake，本机没装 PG driver）。"""
    fake = PgFake({'ledgers': ['id', 'name', 'family_id']})
    assert _is_postgres(fake.engine) is True
    sqlite_engine = create_engine('sqlite:///:memory:')
    assert _is_postgres(sqlite_engine) is False
    sqlite_engine.dispose()


def test_pg_branch_creates_table_and_adds_column(monkeypatch):
    """PG 分支不早退，且发出正确的 DDL 形态。

    #2469 / #2532 两次生产停摆的根因就是「非 SQLite 就跳过」——
    这条测试钉住 PG 侧**真的建表 + 真的加列**，而不是返回 SKIP。
    """
    fake = PgFake({'ledgers': ['id', 'name', 'family_id']})
    fake.install(monkeypatch)

    result = migrate_family_members_ownership(fake.engine)
    assert result.startswith('[OK]')
    assert 'family_members' in fake.columns
    assert 'owner_member_id' in fake.columns['ledgers']
    # PG 侧的加列形态：IF NOT EXISTS（并发友好）
    assert any('ALTER TABLE ledgers ADD COLUMN IF NOT EXISTS owner_member_id' in s for s in fake.sql)
    # 建表形态
    assert any('CREATE TABLE IF NOT EXISTS family_members' in s for s in fake.sql)


def test_pg_branch_is_idempotent(monkeypatch):
    """PG 分支幂等：第二次跑不再发建表/加列 DDL。"""
    fake = PgFake({'ledgers': ['id', 'name', 'family_id']})
    fake.install(monkeypatch)
    migrate_family_members_ownership(fake.engine)
    fake.sql.clear()
    second = migrate_family_members_ownership(fake.engine)
    assert second.startswith('[OK]')
    assert not any('ADD COLUMN' in s for s in fake.sql)


def test_pg_branch_self_check_fails_when_ddl_ignored(monkeypatch):
    """DDL 被静默忽略时必须**抛错**，不能返回「看起来 OK」。

    ``apply_ddl=False`` 模拟「权限不足 / 只读副本」这类 DDL 静默失败的场景。
    """
    fake = PgFake({'ledgers': ['id', 'name', 'family_id']}, apply_ddl=False)
    fake.install(monkeypatch)
    with pytest.raises(RuntimeError):
        migrate_family_members_ownership(fake.engine)


def test_migration_does_not_import_domain_models():
    """core 层不得 import domains 层（``tests/core/test_layer_direction.py`` R1 守卫）。

    这里显式钉住：迁移文件里不能出现 ``app.domains`` 的 import——本仓没有 Alembic，
    ``create_all()`` 又只建缺失的表，存量库的 ``family_members`` 只能靠迁移建出来。
    """
    import inspect as py_inspect

    from app.core import migrations

    src = py_inspect.getsource(migrations)
    assert 'import app.domains' not in src
    assert 'from app.domains' not in src
    assert sqlalchemy is not None  # 仅确认依赖可用

# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库补多用户地基列（家庭隔离，D1）。

背景：v4.7 多用户化后，核心账本表新增 `family_id` 列（默认 1，兼容既有单用户数据），
而 SQLAlchemy 的 `create_all` 不会给已存在的表补列，直接启动会导致
`no such column: family_id`。

本脚本幂等执行：
1. 读取 `app/core/database` 中所有含 `family_id` 列的模型表；
2. 对缺失该列的既有表执行 `ALTER TABLE ... ADD COLUMN family_id INTEGER NOT NULL DEFAULT 1`；
3. 种子默认家庭 1 / 默认用户 1（复用 `_seed_default_identity`）。

用法（在 backend 目录）：
    pdm run python scripts/migrate_family_id.py
"""

import os
import sqlite3
import sys

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


def _family_tables() -> list[str]:
    """收集所有含 family_id 列的表名（含新模型），按创建顺序返回。"""
    # 依次导入模型，确保注册到 Base.metadata
    import app.core.database as db_core
    import app.domains.assets.models  # noqa: F401
    import app.domains.families.models  # noqa: F401
    import app.domains.ledgers.models  # noqa: F401
    import app.domains.portfolios.models  # noqa: F401
    import app.domains.positions.models  # noqa: F401
    import app.domains.strategy.models  # noqa: F401
    import app.domains.transactions.models  # noqa: F401
    import app.domains.users.models  # noqa: F401
    import app.domains.watchlist.models  # noqa: F401

    tables = []
    for table in db_core.Base.metadata.sorted_tables:
        if 'family_id' in {col.name for col in table.columns}:
            tables.append(table.name)
    return tables


def main() -> None:
    db_url = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')
    if not db_url.startswith('sqlite'):
        print('仅支持 SQLite 数据库迁移，当前 DATABASE_URL=%s，请手动处理。' % db_url)
        sys.exit(1)

    # 提取文件路径：sqlite:///./invest.db 或 sqlite:////abs/path.db
    path = db_url.replace('sqlite:///', '', 1)
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    print(f'目标数据库: {path}')
    if not os.path.exists(path):
        print('数据库文件不存在，无需迁移（首次启动将自动建表）。')
        sys.exit(0)

    conn = sqlite3.connect(path)
    try:
        existing = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        for table in _family_tables():
            if table not in existing:
                continue
            cols = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
            if 'family_id' in cols:
                continue
            conn.execute(f'ALTER TABLE {table} ADD COLUMN family_id INTEGER NOT NULL DEFAULT 1')
            print(f'  [OK] {table}: 已添加 family_id（默认 1，归属默认家庭）')
        conn.commit()
    finally:
        conn.close()

    # 种子默认家庭/用户（走 ORM，保证 users/families 两表就绪）
    engine = create_engine('sqlite:///' + path, connect_args={'check_same_thread': False}, poolclass=StaticPool)
    import app.core.database as db_core

    db_core.engine = engine
    db_core.SessionLocal.configure(bind=engine)
    db_core.init_db()
    print('[OK] 默认家庭 1 / 默认用户 1 就绪')


if __name__ == '__main__':
    main()

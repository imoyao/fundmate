# -*- coding: utf-8 -*-
"""为 index_catalog 补核心指数白名单两列（#1365）。

- is_core BOOLEAN（默认 0）
- core_rank INTEGER

SQLite 支持直接 ADD COLUMN，幂等：列已存在时跳过。

用法（在 backend/ 目录下）：
    pdm run python scripts/migrate_index_catalog_core_fields.py
"""

from sqlalchemy import inspect, text

from app.core.db_factory import DOMAIN_MARKET, DatabaseFactory


def main() -> None:
    engine = DatabaseFactory.create(DOMAIN_MARKET)
    insp = inspect(engine)
    if 'index_catalog' not in insp.get_table_names():
        print('[SKIP] index_catalog 表不存在（init_db 建表后即含新列）')
        return
    cols = {c['name'] for c in insp.get_columns('index_catalog')}
    stmts = []
    if 'is_core' not in cols:
        stmts.append('ALTER TABLE index_catalog ADD COLUMN is_core BOOLEAN DEFAULT 0')
    if 'core_rank' not in cols:
        stmts.append('ALTER TABLE index_catalog ADD COLUMN core_rank INTEGER')
    if not stmts:
        print('[SKIP] 新列已存在，无需迁移')
        return
    with engine.connect() as conn:
        for s in stmts:
            conn.execute(text(s))
        conn.commit()
    print(f'[OK] 已加列: {len(stmts)}（is_core / core_rank）')


if __name__ == '__main__':
    main()

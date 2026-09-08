# -*- coding: utf-8 -*-
"""为 index_daily 补 price_mode 口径列（#275 双模式：anchored/normalized）。

SQLite 支持直接 ADD COLUMN，幂等：列已存在时跳过。

用法（在 backend/ 目录下）：
    pdm run python scripts/migrate_index_daily_price_mode.py
"""

from sqlalchemy import inspect, text

from app.core.db_factory import DOMAIN_MARKET, DatabaseFactory


def main() -> None:
    engine = DatabaseFactory.create(DOMAIN_MARKET)
    insp = inspect(engine)
    if 'index_daily' not in insp.get_table_names():
        print('[SKIP] index_daily 表不存在（init_db 建表后即含新列）')
        return
    cols = {c['name'] for c in insp.get_columns('index_daily')}
    if 'price_mode' in cols:
        print('[SKIP] price_mode 列已存在，无需迁移')
        return
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE index_daily ADD COLUMN price_mode VARCHAR(10) DEFAULT 'anchored'"))
        conn.commit()
    print('[OK] 已加列 price_mode（默认 anchored）')


if __name__ == '__main__':
    main()

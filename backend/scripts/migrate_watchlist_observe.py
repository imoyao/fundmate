# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库的 watchlist 表补探市迁移透传列（cost_price/quantity）。

背景：探市观察资产迁移到主站自选（issue #827 B2）需透传观察参考成本价/份额，
而 SQLAlchemy 的 `create_all` 不会给已存在的表补列，直接启动会导致
`no such column: cost_price`。

本脚本幂等执行：
1. 检查 `watchlist` 表是否已有 `cost_price` / `quantity` 列；
2. 对缺失列执行 `ALTER TABLE watchlist ADD COLUMN ...`；
3. 兼容既有 `invest.db`（无需重建 868MB 数据库文件）。

用法（在 backend 目录）：
    pdm run python scripts/migrate_watchlist_observe.py
"""

import os
import sqlite3
import sys

COLUMN_SQL = {
    'cost_price': 'ALTER TABLE watchlist ADD COLUMN cost_price FLOAT',
    'quantity': 'ALTER TABLE watchlist ADD COLUMN quantity FLOAT',
}


def main() -> None:
    db_url = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')
    if not db_url.startswith('sqlite'):
        print('仅支持 SQLite 数据库迁移，当前 DATABASE_URL=%s，请手动处理。' % db_url)
        sys.exit(1)

    path = db_url.replace('sqlite:///', '', 1)
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    print(f'目标数据库: {path}')
    if not os.path.exists(path):
        print('数据库文件不存在，无需迁移（首次启动将自动建表）。')
        sys.exit(0)

    conn = sqlite3.connect(path)
    try:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        if 'watchlist' not in tables:
            print('watchlist 表不存在，无需迁移。')
            sys.exit(0)
        cols = {row[1] for row in conn.execute('PRAGMA table_info(watchlist)')}
        for name, sql in COLUMN_SQL.items():
            if name in cols:
                continue
            conn.execute(sql)
            print(f'  [OK] watchlist: 已添加 {name}')
        conn.commit()
    finally:
        conn.close()
    print('[OK] 探市观察列迁移完成')


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库的 positions 表补 ownership_status 列。

背景：E账户对账/归因（d80d784）给 positions 表新增 ownership_status 列
（active=参与总资产 / shadow=仅对账不参与总资产）。SQLAlchemy 的 `create_all`
不会给已存在的表补列，直接启动会导致 `no such column: positions.ownership_status`。

本脚本幂等执行：
1. 检查 positions 表是否已有 ownership_status 列；
2. 缺失则执行 ALTER TABLE positions ADD COLUMN ownership_status VARCHAR(20)
   NOT NULL DEFAULT 'active'（存量持仓均为真实持仓，统一标记 active）；
3. 兼容既有 invest.db（无需重建 1GB 数据库文件）。

用法（在 backend 目录）：
    pdm run python scripts/migrate_positions_ownership_status.py
"""

import os
import sqlite3
import sys

COLUMN_SQL = 'ALTER TABLE positions ADD COLUMN ownership_status ' "VARCHAR(20) NOT NULL DEFAULT 'active'"


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
        if 'positions' not in tables:
            print('positions 表不存在，无需迁移。')
            sys.exit(0)
        cols = {row[1] for row in conn.execute('PRAGMA table_info(positions)')}
        if 'ownership_status' in cols:
            print('positions 表已含 ownership_status 列，无需迁移。')
            sys.exit(0)
        conn.execute(COLUMN_SQL)
        conn.commit()
        print('  [OK] positions: 已添加 ownership_status（存量默认 active）')
    finally:
        conn.close()
    print('[OK] positions ownership_status 迁移完成')


if __name__ == '__main__':
    main()

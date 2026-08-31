# -*- coding: utf-8 -*-
"""为 asset_snapshots 表补盈亏列（#1220）。

背景：#1220 在 asset_snapshots 扩展 realized_pnl_cents / unrealized_pnl_cents /
total_pnl_cents 三列（整数分）。SQLAlchemy 的 create_all 不会给已存在的表补列，
直接启动会被 database._validate_schema 拦截（缺列即拒绝启动）。本脚本幂等补齐存量库。

用法（在 backend 目录）：
    pdm run python scripts/migrate_snapshot_pnl_columns.py
"""

import os
import sqlite3
import sys

# 直接操作 SQLite 文件，避免拉起整个 ORM 引擎（与 migrate_family_id.py 同范式）。
_NEW_COLUMNS = (
    ('realized_pnl_cents', 'INTEGER NOT NULL DEFAULT 0'),
    ('unrealized_pnl_cents', 'INTEGER NOT NULL DEFAULT 0'),
    ('total_pnl_cents', 'INTEGER NOT NULL DEFAULT 0'),
)


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
        if 'asset_snapshots' not in existing:
            print('asset_snapshots 表不存在，无需迁移。')
            return
        cols = {row[1] for row in conn.execute('PRAGMA table_info(asset_snapshots)')}
        for col, ddl in _NEW_COLUMNS:
            if col in cols:
                continue
            conn.execute(f'ALTER TABLE asset_snapshots ADD COLUMN {col} {ddl}')
            print(f'  [OK] asset_snapshots: 已添加 {col}')
        conn.commit()
    finally:
        conn.close()
    print('[OK] asset_snapshots 盈亏列迁移完成')


if __name__ == '__main__':
    main()

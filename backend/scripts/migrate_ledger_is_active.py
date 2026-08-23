# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库的 ledgers 表补 is_active 列（归档账户能力，见 #1018 关联需求）。

背景：账户管理增强（编辑 + 归档/激活）给 ledgers 表新增 is_active 列
（True=活跃 / False=已归档，归档仅隐藏于日常视图、保留全部数据并仍参与收益计算）。
SQLAlchemy 的 `create_all` 不会给已存在的表补列，启动期 _validate_schema 守卫会
因「表 ledgers 缺列: is_active」拒绝启动。

本脚本幂等执行：
1. 检查 ledgers 表是否已有 is_active 列；
2. 缺失则执行 ALTER TABLE ledgers ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1
   （存量账户均为活跃，统一标记 1）；
3. 兼容既有 invest.db（无需重建数据库文件）。

用法（在 backend 目录）：
    pdm run python scripts/migrate_ledger_is_active.py
"""

import os
import sqlite3
import sys

COLUMN_SQL = 'ALTER TABLE ledgers ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1'


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
        if 'ledgers' not in tables:
            print('ledgers 表不存在，无需迁移。')
            sys.exit(0)
        cols = {row[1] for row in conn.execute('PRAGMA table_info(ledgers)')}
        if 'is_active' in cols:
            print('ledgers 表已含 is_active 列，无需迁移。')
            sys.exit(0)
        conn.execute(COLUMN_SQL)
        conn.commit()
        print('  [OK] ledgers: 已添加 is_active（存量默认 1=活跃）')
    finally:
        conn.close()
    print('[OK] ledgers is_active 迁移完成')


if __name__ == '__main__':
    main()

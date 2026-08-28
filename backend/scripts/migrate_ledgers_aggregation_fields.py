# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库的 ledgers 表补 is_aggregation / frontend_app 列（#1101）。

背景：基金E账户等聚合账本需要从用户账户列表隐藏，新增 is_aggregation 标记；
交易前端（同花顺/东方财富）仅作展示标签，新增 frontend_app 列。
SQLAlchemy create_all 不会给已存在表补列，需本脚本幂等迁移。

用法（在 backend 目录）：
    pdm run python scripts/migrate_ledgers_aggregation_fields.py
"""

import os
import sqlite3
import sys

COLUMNS = [
    ('is_aggregation', 'ALTER TABLE ledgers ADD COLUMN is_aggregation BOOLEAN NOT NULL DEFAULT 0'),
    ('frontend_app', 'ALTER TABLE ledgers ADD COLUMN frontend_app VARCHAR(20)'),
]


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
        for col, sql in COLUMNS:
            if col in cols:
                print(f'ledgers 表已含 {col} 列，跳过。')
                continue
            conn.execute(sql)
            print(f'  [OK] ledgers: 已添加 {col}')
        # 存量 E账户聚合账本补标记（新建的会在导入时置 True）
        if 'is_aggregation' in {row[1] for row in conn.execute('PRAGMA table_info(ledgers)')}:
            cur = conn.execute("UPDATE ledgers SET is_aggregation=1 WHERE ledger_type='e_account' AND is_aggregation=0")
            if cur.rowcount:
                print(f'  [OK] 已将 {cur.rowcount} 个存量 E账户账本标记为聚合账本')
        conn.commit()
    finally:
        conn.close()
    print('[OK] ledgers 聚合字段迁移完成')


if __name__ == '__main__':
    main()

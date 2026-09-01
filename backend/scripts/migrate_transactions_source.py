# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库的 transactions 表补 source 列（#1232 决策 11 / #1238）。

背景：统一对账框架需要流水来源标识（positions.source 已有，transactions 缺失）。
新增 transactions.source 列，复用 PositionSource 枚举（与 positions.source 共用一套）。

**关键约束**：存量 source 一律保持 NULL、不改写——compute_position_hash(source, ...)
以 source 为第一维，改写会导致 import_hash 漂移、破坏去重/幂等（设计文档 §8.2 ⚠️）。
仅新写入的流水按场景落 source（手动记账 manual、对账补录 reconciliation_adjustment、
交易导入 broker source）。

SQLAlchemy create_all 不会给已存在表补列，需本脚本幂等迁移。

用法（在 backend 目录）：
    pdm run python scripts/migrate_transactions_source.py
"""

import os
import sqlite3
import sys

COLUMN = ('source', 'ALTER TABLE transactions ADD COLUMN source VARCHAR(30)')


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
        if 'transactions' not in tables:
            print('transactions 表不存在，无需迁移。')
            sys.exit(0)
        cols = {row[1] for row in conn.execute('PRAGMA table_info(transactions)')}
        col_name, sql = COLUMN
        if col_name in cols:
            print('transactions 表已含 source 列，跳过。')
            sys.exit(0)
        conn.execute(sql)
        conn.commit()
        print('  [OK] transactions: 已添加 source 列（存量保持 NULL，不改写）')
    finally:
        conn.close()
    print('[OK] transactions.source 迁移完成')


if __name__ == '__main__':
    main()

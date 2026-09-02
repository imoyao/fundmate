# -*- coding: utf-8 -*-
"""#863 货基本金口径批次：为存量 SQLite 库补三列。

背景：#863 口径 A（持仓优先）需在 user 域表补货基/收益判定冗余列、在 market 域
money_fund_daily_worth 补数据来源版本列。SQLAlchemy create_all 不会给已存在表补列，
且启动期 schema 校验（app/core/database.py _validate_schema）会直接拒绝启动，故必须迁移。

补列（幂等，缺才加）：
- positions.is_money_fund        BOOLEAN（货基冗余判定，NULL=未判定）
- transactions.is_income         BOOLEAN（收益发放行标记，NULL=未标记）
- money_fund_daily_worth.source_version  VARCHAR(20)（legacy_dirty/v2_recalc）

用法（在 backend 目录）：
    pdm run python scripts/migrate_money_fund_caliber_columns.py [db1 [db2 ...]]
不带参数默认迁移 DATABASE_URL 指向的库 + 同级 invest.user.dev.db（如存在）。

说明：money_fund_daily_worth 的 nav_per_10k 类型统一与 (fund_code,date) 去重重建，
属于 #863 P0-4 数据治理（需 dry-run + 限定代码集），不在本脚本范围。
"""

import os
import sqlite3
import sys

_ADD_COLUMNS = [
    ('positions', 'is_money_fund', 'BOOLEAN'),
    ('transactions', 'is_income', 'BOOLEAN'),
    ('money_fund_daily_worth', 'source_version', 'VARCHAR(20)'),
]


def _resolve_db_paths() -> list[str]:
    """默认迁移库：DATABASE_URL 指向 + 同级 invest.user.dev.db（双库模拟残留）。"""
    db_url = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')
    if not db_url.startswith('sqlite'):
        print(f'仅支持 SQLite 迁移，DATABASE_URL={db_url}，请手动处理。')
        sys.exit(1)
    path = db_url.replace('sqlite:///', '', 1)
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    paths = [path]
    alt = os.path.join(os.path.dirname(path), 'invest.user.dev.db')
    if os.path.exists(alt) and os.path.abspath(alt) != os.path.abspath(path):
        paths.append(alt)
    return paths


def migrate(path: str) -> None:
    print(f'目标数据库: {path}')
    if not os.path.exists(path):
        print('  数据库文件不存在，跳过（首次启动将自动建表）。')
        return
    conn = sqlite3.connect(path)
    try:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        for table, column, ctype in _ADD_COLUMNS:
            if table not in tables:
                print(f'  [skip] {table} 表不存在（新库将自动建表）')
                continue
            cols = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
            if column in cols:
                print(f'  [ok ] {table} 已含 {column}，无需迁移')
                continue
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ctype}')
            conn.commit()
            print(f'  [OK ] {table}: 已添加 {column}')
    finally:
        conn.close()


def main() -> None:
    args = sys.argv[1:]
    paths = list(args) if args else _resolve_db_paths()
    for p in paths:
        migrate(p)
    print('[OK] #863 列迁移完成')


if __name__ == '__main__':
    main()

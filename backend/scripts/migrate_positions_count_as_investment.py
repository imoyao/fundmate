# -*- coding: utf-8 -*-
"""#1354 现金等价物分类收敛：为存量 SQLite 库的 positions 表补两列。

背景：#1354 消弭方案（决策 #3/#7）在 positions 聚合根上加两列：
- positions.count_as_investment  BOOLEAN（持仓级「纳入投资」覆盖项，NULL=未覆盖）
- positions.maturity_date        DATE（逆回购到期日，时间建模真相源；仅 reverse_repo 使用）

SQLAlchemy create_all 不会给已存在表补列，且启动期 schema 校验（app/core/database.py
_validate_schema）会直接拒绝启动，故必须迁移。两列均为可空、无默认值约束，存量数据
NULL 即「未覆盖 / 未到期」，不影响既有口径。

用法（在 backend 目录）：
    pdm run python scripts/migrate_positions_count_as_investment.py [db1 [db2 ...]]
不带参数默认迁移 DATABASE_URL 指向的库 + 同级 invest.user.dev.db（如存在，双库模拟残留）。
"""

import os
import sqlite3
import sys

_ADD_COLUMNS = [
    ('positions', 'count_as_investment', 'BOOLEAN'),
    ('positions', 'maturity_date', 'DATE'),
]


def _resolve_db_paths() -> list[str]:
    """默认迁移库：DATABASE_URL 指向 + 同级 invest.user.dev.db（双库模拟残留）。"""
    db_url = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')
    if not db_url.startswith('sqlite:///'):
        print(f'仅支持 SQLite 迁移，DATABASE_URL={db_url}，请手动处理。')
        sys.exit(1)
    if db_url.startswith('sqlite:///:memory:') or 'file::memory:' in db_url or 'mode=memory' in db_url:
        print('检测到内存数据库，无需迁移。')
        return []
    path = db_url.split('?', 1)[0].replace('sqlite:///', '', 1)
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
                print(f'  [ok ] {table} 已含 {column}')
            else:
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
    print('[OK] #1354 positions 列迁移完成')


if __name__ == '__main__':
    main()

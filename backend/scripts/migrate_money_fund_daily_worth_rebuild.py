# -*- coding: utf-8 -*-
"""#863 P0-4 数据治理：money_fund_daily_worth 去重 + 重建表 + 旧数据标记。

背景：本地 invest.db 该表 122 万行中存在 14,538 组同 (fund_code, date) 重复
（fund_nav_job 与 async_backfill 双写来源）；模型已加 source_version 列并把
nav_per_10k 从 Integer 修为 NUMERIC(10,4)（万份收益单位是「元」），唯一约束
uq_money_fund_daily_worth_code_date 需物理建表才生效（SQLite create_all 不 alter）。

动作（默认 dry-run，--apply 才重建）：
1. 统计：总行数 / (fund_code,date) 去重后行数 / 重复组数；
2. 重建表：CREATE new（与 ORM 列一致 + UNIQUE(fund_code,date)）→
   INSERT 去重数据（GROUP BY fund_code,date）→ DROP old → RENAME new；
3. 旧数据标记：存量行 source_version 置 'legacy_dirty'（NULL→legacy_dirty），
   新数据写入端已标 'v2_recalc'（#863 P0-4 收尾）。

用法（任选目标库，默认 DATABASE_URL）：
    pdm run python scripts/migrate_money_fund_daily_worth_rebuild.py [db_path]
    pdm run python scripts/migrate_money_fund_daily_worth_rebuild.py [db_path] --apply
"""

import argparse
import os
import sqlite3
import sys

_NEW_DDL = """
CREATE TABLE money_fund_daily_worth_new (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    fund_code VARCHAR(6) NOT NULL,
    date DATE NOT NULL,
    nav_per_10k NUMERIC(10, 4),
    annual_return_7d FLOAT,
    source_version VARCHAR(20),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(fund_code) REFERENCES funds (fund_code),
    UNIQUE (fund_code, date)
)
"""


def _stats(conn) -> dict:
    total = conn.execute('SELECT COUNT(*) FROM money_fund_daily_worth').fetchone()[0]
    distinct = conn.execute(
        'SELECT COUNT(*) FROM (SELECT DISTINCT fund_code, date FROM money_fund_daily_worth)'
    ).fetchone()[0]
    dup_groups = conn.execute(
        'SELECT COUNT(*) FROM (SELECT fund_code, date FROM money_fund_daily_worth '
        'GROUP BY fund_code, date HAVING COUNT(*) > 1)'
    ).fetchone()[0]
    legacy = conn.execute(
        'SELECT COUNT(*) FROM money_fund_daily_worth WHERE source_version IS NULL OR source_version <> %s'
        % "'v2_recalc'"
    ).fetchone()[0]
    return {'total': total, 'distinct': distinct, 'dup_groups': dup_groups, 'legacy': legacy}


def _rebuild(conn) -> None:
    conn.execute('PRAGMA foreign_keys=OFF')
    try:
        conn.execute('DROP TABLE IF EXISTS money_fund_daily_worth_new')
        conn.execute(_NEW_DDL)
        conn.execute(
            'INSERT INTO money_fund_daily_worth_new '
            '(fund_code, date, nav_per_10k, annual_return_7d, source_version, created_at, updated_at) '
            'SELECT fund_code, date, nav_per_10k, annual_return_7d, '
            "COALESCE(source_version, 'legacy_dirty'), created_at, updated_at "
            'FROM money_fund_daily_worth GROUP BY fund_code, date'
        )
        conn.execute('DROP TABLE money_fund_daily_worth')
        conn.execute('ALTER TABLE money_fund_daily_worth_new RENAME TO money_fund_daily_worth')
        conn.commit()
    finally:
        conn.execute('PRAGMA foreign_keys=ON')


def main() -> None:
    parser = argparse.ArgumentParser(description='#863 money_fund_daily_worth 去重重建')
    parser.add_argument('db', nargs='?', help='SQLite 库路径（缺省按 DATABASE_URL）')
    parser.add_argument('--apply', action='store_true', help='执行重建；缺省仅 dry-run 统计')
    args = parser.parse_args()

    if args.db:
        path = os.path.abspath(args.db)
    else:
        db_url = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')
        if not db_url.startswith('sqlite'):
            print(f'仅支持 SQLite，DATABASE_URL={db_url}')
            sys.exit(1)
        path = db_url.replace('sqlite:///', '', 1)
        if not os.path.isabs(path):
            path = os.path.abspath(path)

    if not os.path.exists(path):
        print(f'数据库不存在: {path}')
        sys.exit(1)

    conn = sqlite3.connect(path, timeout=30)
    try:
        tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
        if 'money_fund_daily_worth' not in tables:
            print('money_fund_daily_worth 表不存在，跳过')
            return
        st = _stats(conn)
        print(f'目标库: {path}')
        print(f'  当前总行数: {st["total"]}')
        print(f'  去重后行数: {st["distinct"]}（将删除 {st["total"] - st["distinct"]} 行重复）')
        print(f'  重复组数: {st["dup_groups"]}')
        print(f'  待标 legacy_dirty 行: {st["legacy"]}')
        if not args.apply:
            print('  dry-run：以上为将执行的重建计划，--apply 才会重建表并去重。')
            return
        _rebuild(conn)
        st2 = _stats(conn)
        print(f'  [OK] 重建完成：总行数 {st2["total"]}，重复组 {st2["dup_groups"]}，unique 约束已生效')
    finally:
        conn.close()


if __name__ == '__main__':
    main()

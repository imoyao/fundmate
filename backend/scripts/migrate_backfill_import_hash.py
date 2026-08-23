# -*- coding: utf-8 -*-
"""回填 transactions / positions 表中 import_hash 为 NULL 的历史行（#1020 / #1068）。

背景
----
#1065 将去重唯一约束由单列 import_hash 降级为复合 (ledger_id, import_hash)。
import_hash 当前 nullable=True，历史遗留数据存在 NULL（生产库实测：
transactions 11 行、positions 75 行），它们来自导入功能上线前的老数据，无原始哈希。

虽然 SQLite 唯一索引对 NULL 不参与比较（不会因 NULL 炸库），但 #1020 计划要求
回填以消除数据歧义、保证复合约束语义完整，且便于审计追溯。

回填策略（保守、可审计）
------------------------
对 import_hash IS NULL 的行，写入「含主键的占位哈希」：
    transactions: legacy|txn|<id>
    positions:    legacy|pos|<id>
- 含主键 id，绝对唯一，不会与任何正常 md5 哈希冲突，也不会制造假重复；
- 这些历史行因此「永远不会被新导入去重命中」——对上线前的遗留数据正是期望行为
  （它们没有原始交割单来源，不应被当作某次导入的重复）。

与 #1065 的协同
---------------
#1065 的复合约束变更与本草填脚本必须同批上线：先回填消除 NULL，再（或同时）应用
复合约束。本脚本幂等，只更新 NULL 行；重跑安全。

用法（backend 目录）
    pdm run python scripts/migrate_backfill_import_hash.py
"""

import os
import sqlite3
import sys

# (表名, 占位前缀)
TARGETS = [
    ('transactions', 'legacy|txn|'),
    ('positions', 'legacy|pos|'),
]


def backfill_table(conn: sqlite3.Connection, table: str, prefix: str) -> int:
    """回填该表 import_hash 为 NULL 的行，返回回填行数。"""
    null_rows = conn.execute(f'SELECT id FROM {table} WHERE import_hash IS NULL').fetchall()
    if not null_rows:
        print(f'  [SKIP] {table}: 无 NULL import_hash 行')
        return 0
    count = 0
    for (row_id,) in null_rows:
        conn.execute(
            f'UPDATE {table} SET import_hash = ? WHERE id = ?',
            (f'{prefix}{row_id}', row_id),
        )
        count += 1
    print(f'  [OK] {table}: 回填 {count} 行 NULL import_hash（占位 {prefix}<id>）')
    return count


def main() -> None:
    db_url = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')
    if not db_url.startswith('sqlite'):
        print('仅支持 SQLite 迁移，当前 DATABASE_URL=%s，请手动处理。' % db_url)
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
        tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
        total = 0
        for table, prefix in TARGETS:
            if table not in tables:
                print(f'  [SKIP] {table} 表不存在，跳过')
                continue
            total += backfill_table(conn, table, prefix)
        conn.commit()

        # 校验：回填后全表无 NULL
        for table, _ in TARGETS:
            if table not in tables:
                continue
            remain = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE import_hash IS NULL').fetchone()[0]
            if remain:
                print(f'  [FAIL] {table}: 仍有 {remain} 行 NULL，回填异常')
                sys.exit(3)
        print(f'[OK] 回填完成，共 {total} 行；全表 import_hash 无 NULL')
    finally:
        conn.close()


if __name__ == '__main__':
    main()

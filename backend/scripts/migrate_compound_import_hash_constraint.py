# -*- coding: utf-8 -*-
"""将 transactions / positions 表的 import_hash 唯一约束由单列降级为复合 (ledger_id, import_hash)。

背景（#1020 / #1065）：跨账本重导去重作用域从 family 级降到 ledger 级。
import_hash 计算已含 ledger_id，但数据库唯一约束仍为单列 import_hash，语义不对齐，
且无法防御「import_hash 漏含 ledger」路径下的跨账本误判重复。改为复合约束后：
- 同 ledger 内 import_hash 仍唯一（幂等防重）；
- 不同 ledger 可各自导入同一份交割单（放行跨账本重导）。

SQLite 不支持 ALTER ... DROP CONSTRAINT，唯一约束在其内部实现为同名唯一索引，
因此迁移方式为：DROP 旧单列索引 + CREATE 新复合唯一索引。索引名保持与原约束名一致
（uq_txn_import_hash / uq_positions_import_hash），使 SQLAlchemy create_all 对新库
生成的一致、旧库迁移后不重复创建。

安全性：
- 原单列全局唯一约束已保证 import_hash 全局唯一 => 复合 (ledger_id, import_hash) 必然也唯一，
  历史数据不会撞新约束（建索引前脚本会额外校验，发现重复则拒绝并退出）。
- import_hash 为 NULL 的行在唯一索引下不参与比较（SQLite 语义），与改动前行为一致，不退化。

幂等：已为复合（列数==2）则跳过；仍为单列（列数==1）则重建。

用法（在 backend 目录）：
    pdm run python scripts/migrate_compound_import_hash_constraint.py
"""

import os
import sqlite3
import sys

# (表名, 索引名, 复合列)
TARGETS = [
    ('transactions', 'uq_txn_import_hash', ('ledger_id', 'import_hash')),
    ('positions', 'uq_positions_import_hash', ('ledger_id', 'import_hash')),
]


def index_columns(conn: sqlite3.Connection, index_name: str) -> list:
    """返回索引包含的列名列表；索引不存在返回空列表。"""
    rows = conn.execute(f'PRAGMA index_info({index_name})').fetchall()
    # PRAGMA index_info 返回 (seqno, cid, name)
    return [r[2] for r in rows]


def has_duplicate(conn: sqlite3.Connection, table: str, cols: tuple) -> bool:
    """校验是否存在 (ledger_id, import_hash) 完全重复的非 NULL 行。"""
    placeholder = ', '.join(['?'] * len(cols))
    col_list = ', '.join(cols)
    sql = f"""
        SELECT {col_list}, COUNT(*) AS c
        FROM {table}
        WHERE import_hash IS NOT NULL
        GROUP BY {col_list}
        HAVING c > 1
        LIMIT 1
    """
    return conn.execute(sql).fetchone() is not None


def migrate_table(conn: sqlite3.Connection, table: str, index_name: str, cols: tuple) -> None:
    existing = index_columns(conn, index_name)
    if not existing:
        # 索引不存在：直接创建复合唯一索引（兼容全新库但未跑 create_all 的场景）
        col_list = ', '.join(cols)
        conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table} ({col_list})')
        print(f'  [OK] {table}: 创建复合唯一索引 {index_name}({col_list})')
        return

    if existing == list(cols):
        print(f"  [SKIP] {table}: {index_name} 已是复合 ({', '.join(existing)})，无需迁移")
        return

    if len(existing) == 1:
        # 旧单列约束 -> 重建为复合
        if has_duplicate(conn, table, cols):
            print(
                f'  [FAIL] {table}: 存在 (ledger_id, import_hash) 重复数据，拒绝建复合唯一索引。'
                f'请先人工核查数据后再迁移。'
            )
            sys.exit(2)
        conn.execute(f'DROP INDEX {index_name}')
        col_list = ', '.join(cols)
        conn.execute(f'CREATE UNIQUE INDEX {index_name} ON {table} ({col_list})')
        print(f'  [OK] {table}: 单列 {index_name} 重建为复合 ({col_list})')
        return

    print(f"  [WARN] {table}: {index_name} 列定义异常 ({', '.join(existing)})，跳过")


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
        for table, index_name, cols in TARGETS:
            if table not in tables:
                print(f'  [SKIP] {table} 表不存在，跳过')
                continue
            migrate_table(conn, table, index_name, cols)
        conn.commit()
    finally:
        conn.close()
    print('[OK] 复合 import_hash 约束迁移完成')


if __name__ == '__main__':
    main()

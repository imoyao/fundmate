# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库的 ledgers 表补 external_account_code 列（#1100/#1101）。

背景：引入"外部资金账户/凭证"维度，区分同一销售机构下的不同资金账户（普通/两融等），
实现物理隔离而不破坏"一机构一账本"默认。详见
docs/working-notes/ledger-channel-category-redesign-2026-08-28.md §2.5/§6。

- 加列：external_account_code VARCHAR(50) NOT NULL DEFAULT 'MAIN'。
  SQLite 的 ALTER TABLE ADD COLUMN 带 DEFAULT 会直接把存量行填充为 'MAIN'，无需额外回填。
- 部分唯一索引（#1100 计划，演进）：uq_ledger_inst_account ON
  (family_id, sales_institution_id, external_account_code) WHERE sales_institution_id IS NOT NULL。
  若存量存在同机构重复账本（#1100 脏数据），建索引会失败 → 跳过并告警，待 #1100 去重后强制。
  应用层 get_or_create 已按 (family_id, sales_institution_id, external_account_code) 查/建，阻止新重复。

用法（在 backend 目录）：
    pdm run python scripts/migrate_ledgers_external_account_code.py
"""

import os
import sqlite3
import sys

DEFAULT_CODE = 'MAIN'
INDEX_NAME = 'uq_ledger_inst_account'


def _migrate(conn) -> dict:
    """对给定 sqlite3 连接执行迁移，返回执行摘要（便于测试断言）。"""
    info = {
        'added_column': False,
        'index_created': False,
        'index_skipped': False,
        'duplicates': [],
    }
    tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
    if 'ledgers' not in tables:
        return info

    cols = {row[1] for row in conn.execute('PRAGMA table_info(ledgers)')}
    if 'external_account_code' in cols:
        print('ledgers 表已含 external_account_code 列，跳过加列。')
    else:
        # 注意：SQLite ALTER TABLE ADD COLUMN 的 DEFAULT 不接受绑定参数，需内联字面量。
        # NOT NULL DEFAULT 会把存量行直接填充为 'MAIN'，无需额外回填。
        conn.execute(
            "ALTER TABLE ledgers ADD COLUMN external_account_code VARCHAR(50) NOT NULL DEFAULT '%s'" % DEFAULT_CODE
        )
        info['added_column'] = True
        print('  [OK] ledgers: 已添加 external_account_code 列（存量行默认 %s）' % DEFAULT_CODE)

    # 部分唯一索引守卫：先查同机构重复账本（#1100 脏数据）
    dup_rows = conn.execute(
        'SELECT family_id, sales_institution_id, COUNT(*) c FROM ledgers '
        'WHERE sales_institution_id IS NOT NULL '
        'GROUP BY family_id, sales_institution_id HAVING c > 1'
    ).fetchall()
    if dup_rows:
        info['duplicates'] = [tuple(r) for r in dup_rows]
        info['index_skipped'] = True
        print('  [WARN] 检测到同机构重复账本（#1100 脏数据），跳过唯一索引创建，待 #1100 去重后强制：')
        for r in dup_rows:
            print('        family_id=%s, sales_institution_id=%s, 重复数=%s' % (r[0], r[1], r[2]))
    else:
        conn.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS %s '
            'ON ledgers(family_id, sales_institution_id, external_account_code) '
            'WHERE sales_institution_id IS NOT NULL' % INDEX_NAME
        )
        info['index_created'] = True
        print('  [OK] 已创建部分唯一索引 %s（WHERE sales_institution_id IS NOT NULL）' % INDEX_NAME)
    conn.commit()
    return info


def main() -> None:
    db_url = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')
    if not db_url.startswith('sqlite'):
        print('仅支持 SQLite 数据库迁移，当前 DATABASE_URL=%s，请手动处理（含 Postgres 部分唯一索引）。' % db_url)
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
        info = _migrate(conn)
    finally:
        conn.close()
    print('[OK] ledgers external_account_code 迁移完成: %s' % info)


if __name__ == '__main__':
    main()

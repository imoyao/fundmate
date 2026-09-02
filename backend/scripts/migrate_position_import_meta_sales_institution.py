# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库的 position_import_meta 表补 sales_institution_id 列并回填（#1169）。

背景：基金账户归一化到销售机构（设计 B）。PositionImportMeta.fund_account 原为自由文本，
新增 sales_institution_id 外键（指向 sales_institutions，SET NULL）做归一化。

回填规则（设计文档 eastmoney-datasource-and-account-linkage-design-2026-08-30.md 设计 B）：
  - 优先按 ledger_id 关联 ledgers.sales_institution_id 派生；
  - 否则按 source_broker 匹配 AMAC 权威名录（org_name 全称 → display_name 别名，仅 is_active）。

用法（在 backend 目录）：
    pdm run python scripts/migrate_position_import_meta_sales_institution.py
"""

import os
import sqlite3
import sys

TABLE = 'position_import_meta'


def _backfill(conn):
    """幂等回填 sales_institution_id，返回 (ledger 关联命中数, source_broker 匹配命中数)。"""
    # 1) 按 ledger_id 关联 ledgers.sales_institution_id
    ledger_hits = conn.execute(
        """
        UPDATE position_import_meta
        SET sales_institution_id = (
            SELECT l.sales_institution_id FROM ledgers l WHERE l.id = position_import_meta.ledger_id
        )
        WHERE ledger_id IS NOT NULL
          AND sales_institution_id IS NULL
          AND (SELECT l.sales_institution_id FROM ledgers l WHERE l.id = position_import_meta.ledger_id) IS NOT NULL
        """
    ).rowcount

    # 2) 按 source_broker 匹配销售机构（先 org_name 全称，再 display_name 别名）
    rows = conn.execute(
        'SELECT id, source_broker FROM position_import_meta '
        'WHERE source_broker IS NOT NULL AND sales_institution_id IS NULL'
    ).fetchall()
    broker_hits = 0
    for row_id, source_broker in rows:
        inst_id = conn.execute(
            'SELECT id FROM sales_institutions WHERE is_active = 1 AND org_name = ?',
            (source_broker,),
        ).fetchone()
        if inst_id is None:
            inst_id = conn.execute(
                'SELECT id FROM sales_institutions WHERE is_active = 1 AND display_name = ?',
                (source_broker,),
            ).fetchone()
        if inst_id is not None:
            conn.execute(
                'UPDATE position_import_meta SET sales_institution_id = ? WHERE id = ?',
                (inst_id[0], row_id),
            )
            broker_hits += 1
    return ledger_hits, broker_hits


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
        if TABLE not in tables:
            print(f'{TABLE} 表不存在，无需迁移。')
            sys.exit(0)

        cols = {row[1] for row in conn.execute(f'PRAGMA table_info({TABLE})')}
        if 'sales_institution_id' in cols:
            print(f'  [SKIP] {TABLE} 已含 sales_institution_id 列。')
        else:
            conn.execute(
                'ALTER TABLE position_import_meta ADD COLUMN sales_institution_id INTEGER '
                'REFERENCES sales_institutions(id) ON DELETE SET NULL'
            )
            print('  [OK] position_import_meta: 已添加 sales_institution_id 列')

        ledger_hits, broker_hits = _backfill(conn)
        conn.commit()
        print(f'  [OK] 回填完成：ledger 关联命中 {ledger_hits} 行，source_broker 匹配命中 {broker_hits} 行')
    finally:
        conn.close()
    print('[OK] position_import_meta sales_institution_id 迁移完成')


if __name__ == '__main__':
    main()

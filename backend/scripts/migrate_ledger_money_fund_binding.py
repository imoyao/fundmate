# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库的 ledgers 表补类现金产品绑定字段（#1137）。

背景：账户可绑定一个「类现金产品」（余额宝概念，指向 funds.id），
并可选开启「卖出/赎回回款自动申购」。设计见
docs/working-notes/ledger-cash-like-product-binding-2026-08-29.md。

补充两列：
  - linked_money_fund_id      INTEGER（FK funds.id，可空）
  - auto_purchase_money_fund  BOOLEAN NOT NULL DEFAULT 0

两字段均**无需历史回填**：NULL 表示未绑定、0 表示不自动申购，即默认语义
（用户不操作系统不代劳）。脚本幂等，重复执行安全。

用法：
    pdm run python scripts/migrate_ledger_money_fund_binding.py
"""

import os
import sqlite3
import sys

TABLE = 'ledgers'
# (列名, 列定义)
COLUMNS = [
    ('linked_money_fund_id', 'INTEGER'),
    ('auto_purchase_money_fund', 'BOOLEAN NOT NULL DEFAULT 0'),
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
        if TABLE not in tables:
            print(f'{TABLE} 表不存在，无需迁移。')
            sys.exit(0)

        cols = {row[1] for row in conn.execute(f'PRAGMA table_info({TABLE})')}
        added = []
        for col, ddl in COLUMNS:
            if col in cols:
                print(f'  [SKIP] {TABLE} 已含 {col} 列。')
                continue
            conn.execute(f'ALTER TABLE {TABLE} ADD COLUMN {col} {ddl}')
            added.append(col)
            print(f'  [OK] {TABLE}: 已添加 {col} 列')

        conn.commit()
        print(
            f'[OK] {TABLE} 类现金产品绑定字段迁移完成'
            + (f'（本次新增: {", ".join(added)}）' if added else '（无需变更）')
        )
    finally:
        conn.close()


if __name__ == '__main__':
    main()

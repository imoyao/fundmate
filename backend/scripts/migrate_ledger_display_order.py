# -*- coding: utf-8 -*-
"""账本（账户）组内手动排序字段迁移（#1083）。

为 ledgers 表新增 display_order 列（Integer, nullable）。
- 本地开发：默认 ./invest.db（可用 DATABASE_URL 覆盖）。
- 生产（Turso）需另行在 Turso 执行等价 ALTER；本脚本仅覆盖 SQLite 本地库。

用法：
    pdm run python scripts/migrate_ledger_display_order.py            # 检查并执行
    pdm run python scripts/migrate_ledger_display_order.py --check   # 仅检查
"""

import os
import sys

import sqlalchemy
from sqlalchemy import text

DEFAULT_DB = os.environ.get('DATABASE_URL', 'sqlite:///./invest.db')


def main():
    check_only = '--check' in sys.argv
    engine = sqlalchemy.create_engine(DEFAULT_DB)
    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text('PRAGMA table_info(ledgers)')).fetchall()]
        if 'display_order' in cols:
            print('[OK] ledgers.display_order 已存在，无需迁移。')
            return
        if check_only:
            print('[CHECK] 需要迁移：ledgers 缺少 display_order 列。')
            return
        conn.execute(text('ALTER TABLE ledgers ADD COLUMN display_order INTEGER'))
        conn.commit()
        print('[DONE] 已为 ledgers 新增 display_order 列（默认 NULL）。')


if __name__ == '__main__':
    main()

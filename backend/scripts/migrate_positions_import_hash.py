# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库的 positions 表补 #928 去重/溯源列。

背景：issue #928 给 positions 表新增 import_hash / source / source_import_id /
source_broker 四列并加 uq_positions_import_hash 唯一约束。SQLAlchemy 的
`create_all` 不会给已存在的表补列，直接启动会导致 `no such column` 或约束缺失。

本脚本幂等执行：
1. 检查 positions 表是否已有这四列；
2. 对缺失列执行 ALTER TABLE positions ADD COLUMN ...；
3. source 列带 NOT NULL DEFAULT 'manual'（存量数据统一标记为手动来源）；
4. 对齐索引/唯一约束（create_all 不会补，需手动建）：
   - 补建 uq_positions_import_hash 唯一约束（#928 去重治本约束，缺失会放行重复持仓）；
   - 将历史遗留错名索引 idx_positions_asset_type(ledger_id, type) 对齐为模型名
     idx_positions_ledger_asset_type(ledger_id, type)（列相同，仅名称不一致）；
5. 兼容既有 invest.db（无需重建 868MB 数据库文件）。

唯一约束（uq_positions_import_hash）依赖这四列存在，存量数据 import_hash 为 NULL，
NULL 不参与唯一约束冲突，故不会因存量数据撞 key 而失败；新写入由 service 层生成 hash。

用法（在 backend 目录）：
    pdm run python scripts/migrate_positions_import_hash.py
"""

import os
import sqlite3
import sys

# 列名 -> ADD COLUMN SQL（顺序即执行顺序）
COLUMN_SQL = {
    'import_hash': 'ALTER TABLE positions ADD COLUMN import_hash VARCHAR(64)',
    'source': "ALTER TABLE positions ADD COLUMN source VARCHAR(30) NOT NULL DEFAULT 'manual'",
    'source_import_id': 'ALTER TABLE positions ADD COLUMN source_import_id VARCHAR(36)',
    'source_broker': 'ALTER TABLE positions ADD COLUMN source_broker VARCHAR(50)',
}


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
        if 'positions' not in tables:
            print('positions 表不存在，无需迁移。')
            sys.exit(0)
        cols = {row[1] for row in conn.execute('PRAGMA table_info(positions)')}
        for name, sql in COLUMN_SQL.items():
            if name in cols:
                continue
            conn.execute(sql)
            print(f'  [OK] positions: 已添加 {name}')

        # ── 索引/唯一约束对齐（create_all 不补，需手动建）──
        # 1) #928 去重唯一约束：先于重复非 NULL 值做安全检查，避免 CREATE UNIQUE INDEX 因
        #    存量重复数据而失败（SQLite 允许多个 NULL，仅非 NULL 重复会冲突）。
        dup = conn.execute(
            'SELECT import_hash, COUNT(*) c FROM positions '
            'WHERE import_hash IS NOT NULL GROUP BY import_hash HAVING c > 1 LIMIT 1'
        ).fetchone()
        if dup:
            print(f'[WARN] 存在重复 import_hash={dup[0]}，跳过唯一约束创建，请先处理重复数据。')
        else:
            conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_positions_import_hash ' 'ON positions(import_hash)')
            print('  [OK] positions: 已创建唯一约束 uq_positions_import_hash')

        # 2) 复合索引名对齐：模型声明 idx_positions_ledger_asset_type(ledger_id, type)，
        #    DB 历史遗留错名为 idx_positions_asset_type（列相同），统一成模型名。
        conn.execute('DROP INDEX IF EXISTS idx_positions_asset_type')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_positions_ledger_asset_type ' 'ON positions(ledger_id, type)')
        print('  [OK] positions: 已对齐复合索引 idx_positions_ledger_asset_type')

        conn.commit()
    finally:
        conn.close()
    print('[OK] positions 去重/溯源列与索引约束迁移完成')


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""资产快照账户维度字段迁移（#1181）。

为 `asset_snapshots` 增加 `ledger_id` 列，并把幂等 upsert 作用域从
`(family_id, snapshot_date)` 改为 `(family_id, COALESCE(ledger_id, -1), snapshot_date)`。

WHY 必须**重建表**而不是简单 ADD COLUMN
    账户级快照与家庭级快照共存一张表（靠 `ledger_id` 是否为 NULL 区分），
    同一天会出现多行（1 行家庭级 + N 行账户级）。原有 `UNIQUE(family_id, snapshot_date)`
    只允许「一个家庭一天一行」，与多行模型直接冲突；而 SQLite 不支持
    DROP CONSTRAINT / ALTER CONSTRAINT，只能建新表 → 拷数据 → 换名。

    COALESCE(ledger_id, -1) 的原因：SQL 唯一约束中 NULL 互不冲突，家庭级行
    （ledger_id 为 NULL）若不落哨兵就不参与去重，会无限堆积重复行。
    与 `transactions.uq_txn_import_hash` 同范式。

安全护栏（与 `migrate_valuation_mode.py` / `migrate_realized_pnl.py` 同范式）：

1. 默认 **dry-run**：仅打印将执行的 DDL，不写库；显式 `--apply` 才真正执行。
2. 执行前**自动备份**数据库文件（同名 `.bak.<timestamp>`）。
3. **幂等**：列与唯一索引都已存在时直接退出，可重复执行。
4. 整个重建在**单个事务**内完成，任一步失败整体回滚。
5. **保留 AUTOINCREMENT 序列**：换名后同步 `sqlite_sequence`，否则新插入会从
   max(id)+1 之前的空档复用主键，造成 id 冲突。
6. 检测到非 SQLite 连接串时拒绝执行并提示（`asset_snapshots` 属 **user 域**，
   远端 Supabase 需 DBA 执行等价 DDL）。

用法（backend 目录）：

    pdm run python scripts/migrate_asset_snapshot_ledger.py                 # dry-run 预览
    pdm run python scripts/migrate_asset_snapshot_ledger.py --apply         # 真正迁移
    pdm run python scripts/migrate_asset_snapshot_ledger.py --db <path> --apply
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

# asset_snapshots 属 user 域：本地双库模拟时默认回退库为 invest.user.dev.db
_DEFAULT_DB = os.getenv('DATABASE_URL', 'sqlite:///./invest.user.dev.db')

_TABLE = 'asset_snapshots'
_NEW_TABLE = 'asset_snapshots_new'

_CREATE_NEW_SQL = f"""
CREATE TABLE {_NEW_TABLE} (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    family_id INTEGER,
    ledger_id INTEGER,
    snapshot_date DATE NOT NULL,
    total_assets INTEGER NOT NULL,
    total_liabilities INTEGER NOT NULL,
    net_worth INTEGER NOT NULL,
    created_at DATETIME,
    updated_at DATETIME
)
"""

_COPY_SQL = f"""
INSERT INTO {_NEW_TABLE} (
    id, family_id, ledger_id, snapshot_date,
    total_assets, total_liabilities, net_worth, created_at, updated_at
)
SELECT
    id, family_id, NULL, snapshot_date,
    total_assets, total_liabilities, net_worth, created_at, updated_at
FROM {_TABLE}
"""

# 换名后重建的索引；唯一索引是幂等 upsert 的核心
_INDEX_SQLS = (
    f'CREATE INDEX ix_asset_snapshots_family_id ON {_TABLE} (family_id)',
    f'CREATE UNIQUE INDEX uq_asset_snapshots_scope ON {_TABLE} (family_id, COALESCE(ledger_id, -1), snapshot_date)',
    f'CREATE INDEX idx_asset_snapshots_ledger_date ON {_TABLE} (ledger_id, snapshot_date)',
)

_TARGET_COLUMN = 'ledger_id'
_TARGET_INDEX = 'uq_asset_snapshots_scope'


def _resolve_path(db_arg: str) -> str:
    url = db_arg or _DEFAULT_DB

    if url.startswith('sqlite:///'):
        path = url.replace('sqlite:///', '', 1)
    elif '://' in url:
        raise SystemExit(
            f'拒绝执行：连接串不是 SQLite（{url}）。\n'
            f'asset_snapshots 属 user 域，远端库请手工执行等价 DDL：\n'
            f'  1) 建新表 asset_snapshots_new（含 ledger_id INTEGER）\n'
            f'  2) INSERT ... SELECT（ledger_id 置 NULL）\n'
            f'  3) DROP TABLE asset_snapshots; ALTER TABLE asset_snapshots_new RENAME TO asset_snapshots;\n'
            f'  4) CREATE UNIQUE INDEX uq_asset_snapshots_scope ON asset_snapshots '
            f'(family_id, COALESCE(ledger_id, 0), snapshot_date);'
        )
    else:
        path = url

    if not os.path.isabs(path):
        path = os.path.abspath(path)
    return path


def _backup(path: str) -> str:
    stamp = datetime.now().strftime('%Y%m%d%H%M%S')
    bak = f'{path}.bak.{stamp}'
    shutil.copy2(path, bak)
    return bak


def _existing_columns(conn: sqlite3.Connection, table: str) -> set:
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def _existing_indexes(conn: sqlite3.Connection, table: str) -> set:
    return {row[1] for row in conn.execute(f'PRAGMA index_list({table})').fetchall()}


def main() -> int:
    parser = argparse.ArgumentParser(description='资产快照账户维度字段迁移（#1181）')
    parser.add_argument('--db', default='', help='SQLite 路径或 sqlite:/// URL（默认 invest.user.dev.db）')
    parser.add_argument('--apply', action='store_true', help='真正执行；不传则 dry-run 预览')
    parser.add_argument('--no-backup', action='store_true', help='跳过备份（不推荐）')
    args = parser.parse_args()

    path = _resolve_path(args.db)

    # 回退：本地多为单库模式（user 域也落在 invest.db），默认库不存在时自动改用 invest.db
    if not os.path.exists(path) and not args.db:
        fallback = os.path.abspath('invest.db')
        if os.path.exists(fallback):
            print(f'默认库 {path} 不存在，检测到本地单库，改用：{fallback}')
            path = fallback

    if not os.path.exists(path):
        print(f'数据库不存在：{path}')
        return 1

    conn = sqlite3.connect(path)
    try:
        existing_cols = _existing_columns(conn, _TABLE)
        existing_idx = _existing_indexes(conn, _TABLE)

        if _TARGET_COLUMN in existing_cols and _TARGET_INDEX in existing_idx:
            print(f'表 {_TABLE} 已具备 {_TARGET_COLUMN} 列与 {_TARGET_INDEX} 唯一索引，无需迁移（幂等退出）。')
            return 0

        total = conn.execute(f'SELECT COUNT(*) FROM {_TABLE}').fetchone()[0]
        max_id = conn.execute(f'SELECT COALESCE(MAX(id), 0) FROM {_TABLE}').fetchone()[0]

        print(f'目标库：{path}')
        print(f'表 {_TABLE}：{total} 行，当前 max(id)={max_id}')
        print('\n将执行（单事务，失败整体回滚）：')
        print(f'  1) CREATE TABLE {_NEW_TABLE} (... 含 {_TARGET_COLUMN} ...)')
        print(f'  2) INSERT INTO {_NEW_TABLE} SELECT ... FROM {_TABLE}（{_TARGET_COLUMN} 置 NULL，即家庭级行）')
        print(f'  3) DROP TABLE {_TABLE}')
        print(f'  4) ALTER TABLE {_NEW_TABLE} RENAME TO {_TABLE}')
        for sql in _INDEX_SQLS:
            print(f'  5) {sql}')
        print(f'  6) 同步 sqlite_sequence(seq={max_id})，避免主键复用')

        if not args.apply:
            print('\n[dry-run] 未做任何改动。确认无误后加 --apply 执行。')
            return 0

        if not args.no_backup:
            bak = _backup(path)
            print(f'\n已备份：{bak}')

        conn.execute('BEGIN')
        try:
            conn.execute(_CREATE_NEW_SQL)
            conn.execute(_COPY_SQL)
            conn.execute(f'DROP TABLE {_TABLE}')
            conn.execute(f'ALTER TABLE {_NEW_TABLE} RENAME TO {_TABLE}')
            for sql in _INDEX_SQLS:
                conn.execute(sql)

            # AUTOINCREMENT 序列：换名后 sqlite_sequence 里没有新表名的行，
            # 不同步会让后续插入从空闲 id 复用，与快照历史主键冲突。
            has_seq = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
            ).fetchone()
            if has_seq:
                conn.execute('DELETE FROM sqlite_sequence WHERE name=?', (_TABLE,))
                conn.execute('INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)', (_TABLE, max_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        print('\n迁移完成。')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())

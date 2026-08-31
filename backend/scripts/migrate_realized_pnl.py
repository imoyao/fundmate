# -*- coding: utf-8 -*-
"""交易流水已实现盈亏字段迁移（#1183）。

为 `transactions` 表新增一列：

- `realized_pnl` INTEGER DEFAULT 0（该笔流水结转的已实现盈亏，单位：分）

**为什么记在流水而不是持仓**：`position_service.process_sell_or_withdraw` 在
清仓（份额减到 0）时会 `db.delete(position)`。若已实现盈亏记在持仓上，
清仓后这笔已落袋的盈亏会随持仓行一起消失，导致「清仓后查不到已实现盈亏」。
记在流水上则天然保留，且便于删除/回滚流水时自动冲销。

**为什么默认 0**：存量流水没有分摊成本，回填历史已实现盈亏需要按移动加权逐笔重放，
风险高于收益；默认 0 的语义是「未结转」，汇总时对存量数据不产生虚假盈亏。

本脚本安全护栏（与 `migrate_valuation_mode.py` / `migrate_price_units.py` 同范式）：

1. 默认 **dry-run**：仅打印将执行的 DDL，不写库；显式 `--apply` 才真正执行。
2. 执行前**自动备份**数据库文件（同名 `.bak.<timestamp>`）。
3. **幂等**：比对 `PRAGMA table_info`，列已存在则跳过，可重复执行且不丢数据。
4. **数据域提示**：`transactions` 属 **user 域**（见 `app/core/db_factory.py` 的
   `DATA_DOMAIN_REGISTRY`）。双库模式下本脚本只覆盖本地 SQLite 回退库；
   远端 Supabase 需另行执行等价 DDL。检测到非 SQLite 连接串时直接拒绝执行并提示。

用法（backend 目录）：

    pdm run python scripts/migrate_realized_pnl.py                    # dry-run 预览
    pdm run python scripts/migrate_realized_pnl.py --apply            # 真正迁移
    pdm run python scripts/migrate_realized_pnl.py --db <path> --apply
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

# transactions 属 user 域：本地双库模拟时默认回退库为 invest.user.dev.db
_DEFAULT_DB = os.getenv('DATABASE_URL', 'sqlite:///./invest.user.dev.db')

_TABLE = 'transactions'

# (列名, DDL 类型定义)；顺序即执行顺序
_NEW_COLUMNS = (('realized_pnl', 'INTEGER DEFAULT 0'),)


def _resolve_path(db_arg: str) -> str:
    url = db_arg or _DEFAULT_DB

    if url.startswith('sqlite:///'):
        path = url.replace('sqlite:///', '', 1)
    elif '://' in url:
        raise SystemExit(
            f'拒绝执行：连接串不是 SQLite（{url}）。\n'
            f'transactions 属 user 域，远端库请手工执行等价 DDL：\n'
            f'  ALTER TABLE {_TABLE} ADD COLUMN realized_pnl INTEGER DEFAULT 0;'
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
    rows = conn.execute(f'PRAGMA table_info({table})').fetchall()
    return {row[1] for row in rows}  # row[1] = name


def main() -> int:
    parser = argparse.ArgumentParser(description='交易流水已实现盈亏字段迁移（#1183）')
    parser.add_argument('--db', default='', help='SQLite 路径或 sqlite:/// URL（默认 invest.user.dev.db）')
    parser.add_argument('--apply', action='store_true', help='真正执行；不传则 dry-run 预览')
    parser.add_argument('--no-backup', action='store_true', help='跳过备份（不推荐）')
    args = parser.parse_args()

    path = _resolve_path(args.db)

    # 回退：本地多为单库模式（user 域也落在 invest.db），默认库不存在时自动改用 invest.db，
    # 避免「明明有库却报不存在」。显式传 --db 时不回退，尊重调用方意图。
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
        existing = _existing_columns(conn, _TABLE)
        todo = [(name, ddl) for name, ddl in _NEW_COLUMNS if name not in existing]

        total = conn.execute(f'SELECT COUNT(*) FROM {_TABLE}').fetchone()[0]
        print(f'目标库：{path}')
        print(f'表 {_TABLE}：{total} 行')
        if not todo:
            print('所有列均已存在，无需迁移（幂等退出）。')
            return 0

        print('\n将执行：')
        for name, ddl in todo:
            print(f'  ALTER TABLE {_TABLE} ADD COLUMN {name} {ddl};')
        print(f'  UPDATE {_TABLE} SET realized_pnl=0 WHERE realized_pnl IS NULL;')

        if not args.apply:
            print('\n[dry-run] 未做任何改动。确认无误后加 --apply 执行。')
            return 0

        if not args.no_backup:
            bak = _backup(path)
            print(f'\n已备份：{bak}')

        for name, ddl in todo:
            conn.execute(f'ALTER TABLE {_TABLE} ADD COLUMN {name} {ddl}')
            print(f'  已添加列 {name}')

        # 回填：DEFAULT 0 理论上已覆盖存量行，此处兜底（SQLite 加列不带默认值时可能为 NULL）
        cur = conn.execute(f'UPDATE {_TABLE} SET realized_pnl=0 WHERE realized_pnl IS NULL')
        if cur.rowcount:
            print(f'  已回填 realized_pnl=0：{cur.rowcount} 行')
        conn.commit()
        print('\n迁移完成。')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())

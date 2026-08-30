# -*- coding: utf-8 -*-
"""持仓双态计价字段迁移（#1174 / 决策 D1 方案 A）。

为 `positions` 表新增三列：

- `valuation_mode`        TEXT NOT NULL DEFAULT 'nav'（nav=份额×净值 / balance=直接余额）
- `market_value_override` INTEGER NULL（人工录入的可写市值，单位：分）
- `value_override_at`     DATETIME NULL（市值覆写时间，判断新鲜度）

**为什么默认 'nav'**：存量持仓全部是有净值/有市价的标的，默认 nav 保证行为完全不变，
不破坏任何既有数据与市值口径（对应验收「默认值不破坏存量数据」）。

本脚本安全护栏（与 `migrate_price_units.py` 同范式）：

1. 默认 **dry-run**：仅打印将执行的 DDL，不写库；显式 `--apply` 才真正执行。
2. 执行前**自动备份**数据库文件（同名 `.bak.<timestamp>`）。
3. **幂等**：逐列比对 `PRAGMA table_info`，已存在的列跳过，可重复执行且不丢数据。
4. **数据域提示**：`positions` 属 **user 域**（见 `app/core/db_factory.py` 的
   `DATA_DOMAIN_REGISTRY`）。双库模式下本脚本只覆盖本地 SQLite 回退库；
   远端 Supabase 需另行执行等价 DDL。检测到非 SQLite 连接串时直接拒绝执行并提示。

用法（backend 目录）：

    pdm run python scripts/migrate_valuation_mode.py                    # dry-run 预览
    pdm run python scripts/migrate_valuation_mode.py --apply            # 真正迁移
    pdm run python scripts/migrate_valuation_mode.py --db <path> --apply
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

# positions 属 user 域：本地双库模拟时默认回退库为 invest.user.dev.db
_DEFAULT_DB = os.getenv('DATABASE_URL', 'sqlite:///./invest.user.dev.db')

_TABLE = 'positions'

# (列名, DDL 类型定义)；顺序即执行顺序
_NEW_COLUMNS = (
    ('valuation_mode', "TEXT NOT NULL DEFAULT 'nav'"),
    ('market_value_override', 'INTEGER'),
    ('value_override_at', 'DATETIME'),
)


def _resolve_path(db_arg: str) -> str:
    url = db_arg or _DEFAULT_DB

    if url.startswith('sqlite:///'):
        path = url.replace('sqlite:///', '', 1)
    elif '://' in url:
        # 明确的远端连接串（postgres://、libsql:// 等）：SQLite 直连的 DDL 不适用，
        # 拒绝执行避免误判——positions 属 user 域，远端库需由 DBA 执行等价 DDL。
        raise SystemExit(
            f'拒绝执行：连接串不是 SQLite（{url}）。\n'
            f'positions 属 user 域，远端库请手工执行等价 DDL：\n'
            f"  ALTER TABLE {_TABLE} ADD COLUMN valuation_mode TEXT NOT NULL DEFAULT 'nav';\n"
            f'  ALTER TABLE {_TABLE} ADD COLUMN market_value_override INTEGER;\n'
            f'  ALTER TABLE {_TABLE} ADD COLUMN value_override_at DATETIME;'
        )
    else:
        # 裸文件路径（与 migrate_price_units.py 一致）：直接按文件系统路径处理
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
    parser = argparse.ArgumentParser(description='持仓双态计价字段迁移（#1174）')
    parser.add_argument('--db', default='', help='SQLite 路径或 sqlite:/// URL（默认 invest.user.dev.db）')
    parser.add_argument('--apply', action='store_true', help='真正执行；不传则 dry-run 预览')
    parser.add_argument('--no-backup', action='store_true', help='跳过备份（不推荐）')
    args = parser.parse_args()

    path = _resolve_path(args.db)
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
        print(f"  UPDATE {_TABLE} SET valuation_mode='nav' WHERE valuation_mode IS NULL OR valuation_mode='';")

        if not args.apply:
            print('\n[dry-run] 未做任何改动。确认无误后加 --apply 执行。')
            return 0

        if not args.no_backup:
            bak = _backup(path)
            print(f'\n已备份：{bak}')

        for name, ddl in todo:
            conn.execute(f'ALTER TABLE {_TABLE} ADD COLUMN {name} {ddl}')
            print(f'  已添加列 {name}')

        # 回填：理论上 NOT NULL DEFAULT 'nav' 已覆盖存量行，此处兜底空串/异常值
        cur = conn.execute(
            f"UPDATE {_TABLE} SET valuation_mode='nav' WHERE valuation_mode IS NULL OR valuation_mode=''"
        )
        if cur.rowcount:
            print(f"  已回填 valuation_mode='nav'：{cur.rowcount} 行")
        conn.commit()
        print('\n迁移完成。')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())

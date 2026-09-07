# -*- coding: utf-8 -*-
"""修复账户改名未同步的 account_name 冗余快照（issue #1354）。

背景（根因）：
assets / positions / transactions 三张表都冗余了 account_name 列（ledgers.name 的快照）。
历史实现里 PATCH /api/ledgers/<id>/ 只改 ledgers.name，没有级联刷新这三张表，
导致「账本改名了，明细里还是旧名字」。

代码侧已修好（ledgers/views._sync_account_name_snapshots 在改名时级联刷新），
本脚本负责清理**存量漂移数据**：把 ledger_id 命中且 account_name 与账户当前名不一致的
行，统一刷成账户当前名。

用法（backend 目录）：
pdm run python scripts/repair_account_name_snapshots.py                 # DRY-RUN（默认，只统计）
pdm run python scripts/repair_account_name_snapshots.py --apply         # 备份后执行修复
pdm run python scripts/repair_account_name_snapshots.py --rollback      # 从备份表还原
pdm run python scripts/repair_account_name_snapshots.py --db <path>     # 指定库文件

安全措施：
- 默认 DRY-RUN，不写库；
- --apply 前把受影响行的 (id, ledger_id, account_name) 备份到
  <table>_name_repair_backup_<date>；
- --rollback 从备份表还原，备份表保留不删，可重复回滚。
"""

import argparse
import sqlite3
from datetime import date
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / 'invest.db'

# 待修复的三张表：都冗余了 account_name，且都以 ledger_id 指向 ledgers
TARGET_TABLES = ('assets', 'positions', 'transactions')

DETECT_SQL = """
SELECT x.id, x.ledger_id, x.account_name, l.name AS ledger_name
FROM {table} x
JOIN ledgers l ON l.id = x.ledger_id
WHERE x.ledger_id IS NOT NULL
  AND (x.account_name IS NULL OR x.account_name <> l.name)
ORDER BY x.id
"""


def detect(cur, table):
    """找出该表上 account_name 与账户当前名不一致的行。"""
    return cur.execute(DETECT_SQL.format(table=table)).fetchall()


def scan(cur):
    return {t: detect(cur, t) for t in TARGET_TABLES}


def ensure_backup(cur, table, rows, suffix):
    backup_table = f'{table}_name_repair_backup_{suffix}'
    cur.execute(
        f'CREATE TABLE IF NOT EXISTS {backup_table} (id INTEGER PRIMARY KEY, ledger_id INTEGER, account_name TEXT)'
    )
    cur.executemany(
        f'INSERT OR REPLACE INTO {backup_table} (id, ledger_id, account_name) VALUES (?, ?, ?)',
        [(r[0], r[1], r[2]) for r in rows],
    )
    return backup_table


def apply_fix(cur, table, rows):
    cur.executemany(f'UPDATE {table} SET account_name = ? WHERE id = ?', [(r[3], r[0]) for r in rows])
    return len(rows)


def rollback(cur, suffix):
    restored = {}
    for table in TARGET_TABLES:
        backup_table = f'{table}_name_repair_backup_{suffix}'
        exists = cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (backup_table,)).fetchone()
        if not exists:
            restored[table] = 'no-backup'
            continue
        cur.execute(
            f'UPDATE {table} SET account_name = ('
            f'  SELECT b.account_name FROM {backup_table} b WHERE b.id = {table}.id'
            f') WHERE id IN (SELECT id FROM {backup_table})'
        )
        restored[table] = cur.rowcount
    return restored


def _detect_latest_backup_suffix(cur) -> str | None:
    """从 sqlite_master 探测最近的 name_repair_backup 后缀（取日期字符串最大值）。

    备份表命名 ``<table>_name_repair_backup_<suffix>``，按 suffix 字典序（YYYYMMDD）取最大即最近。
    """
    rows = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_name_repair_backup_%'"
    ).fetchall()
    suffixes = {r[0].rsplit('_name_repair_backup_', 1)[-1] for r in rows if '_name_repair_backup_' in r[0]}
    return max(suffixes) if suffixes else None


def main():
    parser = argparse.ArgumentParser(description='修复 account_name 快照与账户改名不同步（#1354）')
    parser.add_argument('--db', default=str(DEFAULT_DB), help='SQLite 库文件路径')
    parser.add_argument('--apply', action='store_true', help='真正写库（默认 DRY-RUN）')
    parser.add_argument('--rollback', action='store_true', help='从备份表还原')
    parser.add_argument('--backup-suffix', default=date.today().strftime('%Y%m%d'), help='备份表后缀')
    args = parser.parse_args()

    # #1355 AI review：--backup-suffix 会被拼入 CREATE TABLE / UPDATE 标识符，
    # 含引号或分号可造成 SQL 注入 / 语法错误，用白名单校验（字母、数字、下划线、连字符）。
    if not all(c.isalnum() or c in '_-' for c in args.backup_suffix):
        parser.error('--backup-suffix 只能包含字母、数字、下划线或连字符')

    # #1355 AI review：sqlite3.connect 在路径不存在时会新建空库，导致误报「无漂移」并跳过修复；
    # 连接前先校验文件确实存在。
    if not Path(args.db).is_file():
        parser.error(f'数据库文件不存在: {args.db}')

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    if args.rollback:
        suffix = args.backup_suffix
        # #1355 AI review：未显式指定 suffix 时，自动探测最近一次备份（避免隔天 rollback 找不到备份表）。
        if suffix == date.today().strftime('%Y%m%d'):
            detected = _detect_latest_backup_suffix(cur)
            if detected:
                suffix = detected
        restored = rollback(cur, suffix)
        conn.commit()
        print(f'[rollback] 已从备份（后缀 {suffix}）还原：{restored}')
        conn.close()
        return

    found = scan(cur)
    total = sum(len(v) for v in found.values())
    for table, rows in found.items():
        print(f'[{table}] 待修复 {len(rows)} 行')
        for r in rows[:10]:
            print(f'    id={r[0]} ledger_id={r[1]} account_name={r[2]!r} -> {r[3]!r}')
        if len(rows) > 10:
            print(f'    ... 其余 {len(rows) - 10} 行省略')

    if total == 0:
        print('[done] 无漂移数据，无需修复')
        conn.close()
        return

    if not args.apply:
        print(f'[dry-run] 共 {total} 行待修复；加 --apply 执行（会先建备份表）')
        conn.close()
        return

    # #1355 AI review：先建全部备份表 + 写入备份行，再统一执行修复 UPDATE，最后单次 commit。
    # 避免「备份 DDL 隐式提交」导致前表 UPDATE 提前落库、后表失败时出现「部分修复」且无法整体回滚。
    backups = {}
    for table, rows in found.items():
        if not rows:
            continue
        backups[table] = ensure_backup(cur, table, rows, args.backup_suffix)
    fixed = {}
    for table, rows in found.items():
        if not rows:
            continue
        fixed[table] = apply_fix(cur, table, rows)
    conn.commit()
    print(f'[apply] 已修复：{fixed}')
    print(f'[apply] 备份表：{backups}（可用 --rollback 还原）')
    conn.close()


if __name__ == '__main__':
    main()

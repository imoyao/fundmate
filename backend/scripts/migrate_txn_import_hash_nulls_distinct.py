# -*- coding: utf-8 -*-
"""交易表幂等键约束修正：让 NULL ledger_id 也参与 import_hash 去重。

背景：
    原约束 UNIQUE(ledger_id, import_hash) 在 ledger_id 为 NULL（未归档持仓 /
    探市迁移）时，因唯一约束中 NULL 互不冲突，导致 (NULL, import_hash) 无法去重。
    于是「网络超时重发」或「探市迁移重跑」会在 transactions 表写入重复流水
    （持仓因 process_buy_or_deposit 合并而数量正确，但交易明细被重复）。

    修复：改用函数式唯一索引 (COALESCE(ledger_id, -1), import_hash)。
    NULL 落到哨兵 -1 后参与去重；存量 NULL import_hash 行第二列仍为 NULL → 元组不冲突，不受影响。

安全护栏（与 migrate_price_units.py 一致）：
    1. 默认指向运行库 invest.db，可用 --db 或 DATABASE_URL 覆盖。
    2. 执行前自动备份数据库文件（同名 .bak.<timestamp>）。
    3. 默认 dry-run：仅打印将执行的 DDL 与冲突检测，不写库；--apply 才真正执行。
    4. 幂等守卫：新索引已存在则视为已迁移，直接退出；若检测到会导致新索引冲突的
       存量重复行， dry-run 警告，--apply 需加 --force 才执行（避免创建索引失败）。

注意：本脚本面向 SQLite（invest.db）。若生产库为 PostgreSQL，请用等价 DDL：
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS uq_txn_import_hash;
    CREATE UNIQUE INDEX uq_txn_import_hash
        ON transactions (COALESCE(ledger_id, -1), import_hash);

用法（backend 目录）：
    pdm run python scripts/migrate_txn_import_hash_nulls_distinct.py            # dry-run 预览
    pdm run python scripts/migrate_txn_import_hash_nulls_distinct.py --apply    # 真正执行
    pdm run python scripts/migrate_txn_import_hash_nulls_distinct.py --db /path/to/db.sqlite --apply
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

_DEFAULT_DB = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')
_INDEX = 'uq_txn_import_hash'
_OLD_DDL = f'DROP INDEX IF EXISTS {_INDEX}'
_NEW_DDL = f'CREATE UNIQUE INDEX {_INDEX} ON transactions (COALESCE(ledger_id, -1), import_hash)'


def _resolve_path(db_arg: str) -> str:
    url = db_arg or _DEFAULT_DB
    if url.startswith('sqlite:///'):
        url = url.replace('sqlite:///', '', 1)
    if not os.path.isabs(url):
        url = os.path.abspath(url)
    return url


def _backup(path: str) -> str:
    stamp = datetime.now().strftime('%Y%m%d%H%M%S')
    bak = f'{path}.bak.{stamp}'
    shutil.copy2(path, bak)
    return bak


def _index_exists(conn: sqlite3.Connection) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (_INDEX,))
    return cur.fetchone() is not None


def _find_conflicts(conn: sqlite3.Connection) -> list:
    """定位会导致新函数式唯一索引冲突的存量重复行。

    仅当 (COALESCE(ledger_id,-1), import_hash) 分组数>1 且 import_hash 非 NULL 时才冲突。
    """
    rows = conn.execute(
        'SELECT COALESCE(ledger_id, -1) AS lk, import_hash, COUNT(*) AS c '
        'FROM transactions WHERE import_hash IS NOT NULL '
        'GROUP BY lk, import_hash HAVING c > 1'
    ).fetchall()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description='交易表 import_hash 去重约束修正（NULL ledger_id 参与去重）')
    parser.add_argument('--db', default=None, help='数据库路径（默认 invest.db）')
    parser.add_argument('--apply', action='store_true', help='真正执行 DDL（默认仅 dry-run 预览）')
    parser.add_argument('--force', action='store_true', help='存在冲突行时仍强制执行（先备份）')
    args = parser.parse_args()

    path = _resolve_path(args.db)
    print(f'目标数据库: {path}')
    if not os.path.exists(path):
        print('数据库文件不存在，无需迁移（首次启动将自动按新模型建表）。')
        sys.exit(0)

    conn = sqlite3.connect(path)
    try:
        tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
        if 'transactions' not in tables:
            print('transactions 表不存在，无需迁移。')
            sys.exit(0)

        # 幂等守卫：新索引已存在 → 视为已迁移
        if _index_exists(conn):
            print(f'[守卫] 唯一索引 {_INDEX} 已存在，无需迁移。')
            sys.exit(0)

        conflicts = _find_conflicts(conn)
        if conflicts:
            print(
                f'[警告] 检测到 {len(conflicts)} 组会导致新唯一索引冲突的存量重复行'
                f'（ledger 分组, import_hash, 重复数）：'
            )
            for lk, h, c in conflicts:
                print(f'    ({lk}, {h!r}) x{c}')
            if not args.force:
                print('        请先人工核查/清理重复行，或确认无误后加 --force 强制执行（会先备份）。')
                sys.exit(1)
            print('[--force] 已确认，将继续执行（冲突行可能因索引创建失败而需手动处理）。')

        print(f'  [预览] DROP 旧约束/索引: {_OLD_DDL}')
        print(f'  [预览] CREATE 新函数式唯一索引: {_NEW_DDL}')

        if not args.apply:
            print('\n（dry-run）未做任何修改。确认无误后加 --apply 执行；执行前会自动备份。')
            sys.exit(0)

        bak = _backup(path)
        print(f'  [OK] 已备份至 {bak}')

        conn.execute(_OLD_DDL)
        print(f'  [OK] 已删除旧约束/索引 {_INDEX}')
        conn.execute(_NEW_DDL)
        conn.commit()
        print(f'[OK] 已创建函数式唯一索引 {_INDEX}（COALESCE(ledger_id, -1), import_hash）。')
        print('        此后未归档/探市(re)导入将按 import_hash 正确去重，不再产生重复流水。')
    finally:
        conn.close()


if __name__ == '__main__':
    main()

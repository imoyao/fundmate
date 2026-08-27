# -*- coding: utf-8 -*-
"""持仓/交易价格单位迁移：分(×100) → 0.0001元(×10000)。

背景：issue #1099 将 positions.avg_price / positions.current_price /
transactions.price 的存储单位从「分」(×100) 改为「0.0001元」(×10000)，
以支持 4 位小数价格精度。存量数据需整体 ×100 完成单位换算。

本脚本安全护栏：
1. 默认指向实际运行库（invest.db，与 repair_price_scale.py 一致）；
   可通过 --db 或 DATABASE_URL 覆盖（双库/Supabase 模式请手动指定）。
2. 执行前自动备份数据库文件（同名 .bak.<timestamp>）。
3. 默认 dry-run：仅打印将受影响的行数，不写库；显式 --apply 才真正执行 UPDATE。
4. **幂等守卫（防重复执行）**：正向迁移 ×100 若检测到数据已是目标单位
   （用 transactions.amount÷quantity 不变量校验），将拒绝执行并提示改用 --force，
   避免把已正确的数据再 ×100（这正是历史脏数据的成因）。
5. --rollback 用备份反向 ÷100（仅在确认迁移出错时手动使用，依赖刚才的备份）。

用法（backend 目录）：
    pdm run python scripts/migrate_price_units.py            # dry-run 预览
    pdm run python scripts/migrate_price_units.py --apply    # 真正迁移
    pdm run python scripts/migrate_price_units.py --db /path/to/db.sqlite --apply
    pdm run python scripts/migrate_price_units.py --force --apply   # 强制（绕过幂等守卫）
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

_DEFAULT_DB = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')

PRICE_UNIT = 10000
CENT = 100
MIN_UNIT = 10000


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


def _count(conn: sqlite3.Connection, table: str, col: str) -> int:
    cur = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL')
    return cur.fetchone()[0]


def _already_migrated(conn: sqlite3.Connection) -> tuple[bool, str]:
    """用 amount÷quantity 不变量判断交易价格是否已处于目标单位（0.0001元）。

    返回 (是否已迁移, 诊断信息)。若采样中「存储价≈推导价」占比 ≥80%，判定已迁移。
    仅正向迁移需要此守卫；反向回滚是人工恢复，不依赖此判断。
    """
    rows = conn.execute(
        'SELECT price, quantity, amount FROM transactions '
        "WHERE type IN ('buy','sell','deposit') AND quantity>0 AND amount>0 AND price>0"
    ).fetchall()
    if rows:
        ok = 0
        for price, qty, amount in rows:
            stored_yuan = price / PRICE_UNIT
            expected_yuan = (amount / CENT) / (qty / MIN_UNIT)
            if expected_yuan <= 0:
                continue
            ratio = expected_yuan / stored_yuan
            if 0.5 <= ratio <= 2.0:
                ok += 1
        frac = ok / len(rows)
        detail = f'交易采样 {len(rows)} 行，存储价≈推导价 占比 {frac:.0%}'
        return frac >= 0.8, detail

    # 无交易可校验时，退回持仓均价量级判断（基金净值通常在 0.05~50 元 → 500~500000 价格单位）
    pos = conn.execute(
        'SELECT COUNT(*), SUM(CASE WHEN avg_price BETWEEN 500 AND 500000 THEN 1 ELSE 0 END) '
        'FROM positions WHERE avg_price IS NOT NULL'
    ).fetchall()
    if pos and pos[0][0]:
        total, plaus = pos[0]
        plaus = plaus or 0
        frac = plaus / total
        detail = f'持仓采样 {total} 行，均价处于合理量级 占比 {frac:.0%}'
        return frac >= 0.8, detail

    return False, '无足够采样行，无法判定（按未迁移处理）'


def main() -> None:
    parser = argparse.ArgumentParser(description='价格单位迁移：分 → 0.0001元')
    parser.add_argument('--db', default=None, help='数据库路径（默认 invest.db）')
    parser.add_argument('--apply', action='store_true', help='真正执行迁移（默认仅 dry-run 预览）')
    parser.add_argument('--rollback', action='store_true', help='反向 ÷100 回滚（仅迁移出错时手动使用）')
    parser.add_argument('--force', action='store_true', help='绕过幂等守卫，强制执行（慎用）')
    args = parser.parse_args()

    path = _resolve_path(args.db)
    print(f'目标数据库: {path}')
    if not os.path.exists(path):
        print('数据库文件不存在，无需迁移（首次启动将自动建表）。')
        sys.exit(0)

    factor = 1 / 100 if args.rollback else 100
    verb = '回滚 ÷100' if args.rollback else '迁移 ×100'

    conn = sqlite3.connect(path)
    try:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}

        targets = []
        if 'positions' in tables:
            targets.append(('positions', ['avg_price', 'current_price']))
        if 'transactions' in tables:
            targets.append(('transactions', ['price']))

        if not targets:
            print('positions / transactions 表均不存在，无需迁移。')
            sys.exit(0)

        # 幂等守卫：仅正向迁移需要；回滚是人工恢复，不拦截
        if not args.rollback and not args.force:
            migrated, detail = _already_migrated(conn)
            if migrated:
                print(f'[守卫] 检测到数据疑似已是目标单位（{detail}）。')
                print('        正向 ×100 会损坏已正确的数据；若确属误判，请先备份后再加 --force 强制执行。')
                sys.exit(0)
            else:
                print(f'[守卫] 数据疑似仍处旧单位（{detail}），允许迁移。')

        # dry-run 预览
        for table, cols in targets:
            for col in cols:
                n = _count(conn, table, col)
                print(f'  [预览] {table}.{col}: {n} 行将{verb}')

        if not args.apply:
            print('\n（dry-run）未做任何修改。确认无误后加 --apply 执行；执行前会自动备份。')
            sys.exit(0)

        bak = _backup(path)
        print(f'  [OK] 已备份至 {bak}')

        total = 0
        for table, cols in targets:
            for col in cols:
                sql = f'UPDATE {table} SET {col} = {col} * {factor} WHERE {col} IS NOT NULL'
                conn.execute(sql)
                n = _count(conn, table, col)
                total += n
                print(f'  [OK] {table}.{col}: 已{verb}')
        conn.commit()
        print(f'[OK] 价格单位迁移完成（共 {total} 列次更新）。回滚请用 --rollback（依赖刚才的备份）。')
    finally:
        conn.close()


if __name__ == '__main__':
    main()

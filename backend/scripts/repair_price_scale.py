# -*- coding: utf-8 -*-
"""价格/净值缩放修复：依据 amount×quantity 不变量归一化 transactions.price 与 positions 价格。

背景：
    价格单位统一为 0.0001 元（×10000）、金额为分（×100）、份额为最小单位（×10000）。
    历史迁移（migrate_price_units.py）曾对部分 transactions.price 重复执行 ×100，
    导致个别记录被放大/缩小 100 倍（例如某基金买入价存储为 4,503,800，实际应为 45,038），
    而同基金的 positions.avg_price 却是正确的——数据处于「混合缩放」状态，
    表现为「有的接口对、有的接口错」。

修复思路（不依赖记录当前缩放，而是从可信字段反推）：
    1. 交易的 price 可由 amount、quantity 推导：
        价格(元) = (amount/100) / (quantity/10000) = amount * 100 / quantity
        再 ×10000 存为 price_units。amount(分) 与 quantity(最小单位) 经核对是正确的。
        —— 仅当「推导价 / 存储价」偏离 ≥10 倍（明显错缩放）时才修正，避免扰动正常记录。
    2. positions.avg_price 由该持仓买入/定投交易（已修复）的加权均价重算；
        仅当与现有值偏离 ≥2 倍时才写回，保持与交易一致。
    3. positions.current_price 与 avg_price 同为「每单位价格」，二者应在同一量级；
        若 current_price/avg_price 偏离 ≥10 倍且纠正后落在 avg_price 的 0.5~2 倍内，
        则按 10^k 因子归一化。

实现要点：所有修正先在内存中算出「有效值」，再据此计算后续字段，
          保证 dry-run 与 --apply 看到的数值完全一致，且绝不改动本来正确的数据。

安全护栏（与 migrate_price_units.py 一致）：
    - 执行前自动备份数据库（同名 .bak.<timestamp>）；
    - 默认 dry-run：仅打印将受影响的行，不写库；
    - 显式 --apply 才真正执行 UPDATE。

用法（backend 目录）：
    pdm run python scripts/repair_price_scale.py            # dry-run 预览
    pdm run python scripts/repair_price_scale.py --apply    # 真正修复
    pdm run python scripts/repair_price_scale.py --db /path/to/invest.db --apply
"""

import argparse
import math
import os
import shutil
import sqlite3
import sys
from datetime import datetime

_DEFAULT_DB = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')

# 价格单位：1 元 = 10000 价格单位；1 元 = 100 分；1 份 = 10000 最小单位
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


def _round_int(x: float) -> int:
    return int(round(x))


def main() -> None:
    parser = argparse.ArgumentParser(description='价格/净值缩放修复（amount×quantity 不变量）')
    parser.add_argument('--db', default=None, help='数据库路径（默认 invest.db）')
    parser.add_argument('--apply', action='store_true', help='真正执行修复（默认仅 dry-run 预览）')
    args = parser.parse_args()

    path = _resolve_path(args.db)
    print(f'目标数据库: {path}')
    if not os.path.exists(path):
        print('数据库文件不存在，无需修复。')
        sys.exit(0)

    conn = sqlite3.connect(path)
    try:
        tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
        if 'transactions' not in tables or 'positions' not in tables:
            print('transactions / positions 表不存在，无需修复。')
            sys.exit(0)

        # ---- Phase A: 交易价格（内存中计算有效值）----
        print('\n=== transactions.price（由 amount×quantity 推导）===')
        txn_rows = conn.execute(
            'SELECT id, type, price, quantity, amount FROM transactions '
            "WHERE type IN ('buy','sell','deposit') AND quantity IS NOT NULL AND quantity > 0 "
            'AND amount IS NOT NULL AND price IS NOT NULL AND price > 0'
        ).fetchall()
        txn_eff = {}  # id -> 有效 price_units
        txn_fixes = []  # (id, type, old_price, new_price, stored_yuan, expected_yuan, ratio)
        for tid, ttype, price, qty, amount in txn_rows:
            stored_yuan = price / PRICE_UNIT
            expected_yuan = (amount / CENT) / (qty / MIN_UNIT)
            if expected_yuan <= 0:
                txn_eff[tid] = price
                continue
            ratio = expected_yuan / stored_yuan
            if ratio >= 10 or ratio <= 0.1:
                new_price = _round_int(expected_yuan * PRICE_UNIT)
                txn_fixes.append((tid, ttype, price, new_price, stored_yuan, expected_yuan, ratio))
                txn_eff[tid] = new_price
            else:
                txn_eff[tid] = price
        for tid, ttype, price, new_price, stored_yuan, expected_yuan, ratio in txn_fixes:
            print(
                f'  [txn] id={tid} {ttype}: price {price} -> {new_price} '
                f'(存储 {stored_yuan:.4f}元, 推导 {expected_yuan:.4f}元, '
                f'存储价为推导价的 {stored_yuan / expected_yuan:.0f}x)'
            )
        print(f'  transactions.price: 待修复 {len(txn_fixes)} 行')

        # ---- Phase B: 持仓均价（用 Phase A 的有效交易价）----
        print('\n=== positions.avg_price（由买入交易加权均价）===')
        by_position = {}
        for tid, pid, price, qty in conn.execute(
            'SELECT id, position_id, price, quantity FROM transactions '
            "WHERE type IN ('buy','deposit') AND quantity IS NOT NULL AND quantity > 0 "
            'AND price IS NOT NULL AND price > 0'
        ).fetchall():
            by_position.setdefault(pid, []).append((txn_eff.get(tid, price), qty))

        avg_eff = {}
        avg_fixes = []  # (pid, old_avg, new_avg, computed, ratio_or_None)
        for pid, avg_price, _pos_qty in conn.execute('SELECT id, avg_price, quantity FROM positions').fetchall():
            txns = by_position.get(pid)
            if not txns:
                avg_eff[pid] = avg_price
                continue
            num = sum(t_price * t_qty for t_price, t_qty in txns)
            den = sum(t_qty for _t_price, t_qty in txns)
            if den <= 0:
                avg_eff[pid] = avg_price
                continue
            computed = num / den
            if avg_price is None or avg_price <= 0:
                new_avg = _round_int(computed)
                avg_fixes.append((pid, None, new_avg, computed, None))
                avg_eff[pid] = new_avg
            else:
                ratio = computed / avg_price
                if ratio >= 2 or ratio <= 0.5:
                    new_avg = _round_int(computed)
                    avg_fixes.append((pid, avg_price, new_avg, computed, ratio))
                    avg_eff[pid] = new_avg
                else:
                    avg_eff[pid] = avg_price
        for pid, old_avg, new_avg, computed, ratio in avg_fixes:
            if old_avg is None:
                print(f'  [pos] id={pid}: avg_price NULL -> {new_avg} (由交易推算 {computed:.2f})')
            else:
                print(f'  [pos] id={pid}: avg_price {old_avg} -> {new_avg} (推算 {computed:.2f}, 偏差 {ratio:.1f}x)')
        print(f'  positions.avg_price: 待修复 {len(avg_fixes)} 行')

        # ---- Phase C: 当前价（与有效 avg_price 同量级）----
        print('\n=== positions.current_price（与 avg_price 同量级归一化）===')
        cur_fixes = []  # (pid, type, old_cur, new_cur, factor)
        for pid, ptype, current_price in conn.execute(
            'SELECT id, type, current_price FROM positions WHERE current_price IS NOT NULL AND current_price > 0'
        ).fetchall():
            avg_price = avg_eff.get(pid)
            if not avg_price or avg_price <= 0:
                continue
            ratio = current_price / avg_price
            if ratio < 10 and ratio > 0.1:
                continue
            k = round(math.log10(ratio))
            factor = 10**k
            corrected = current_price / factor
            if not (0.5 <= corrected / avg_price <= 2.0):
                continue
            new_cur = _round_int(corrected)
            cur_fixes.append((pid, ptype, current_price, new_cur, factor))
        for pid, ptype, current_price, new_cur, factor in cur_fixes:
            print(f'  [pos] id={pid} type={ptype}: current_price {current_price} -> {new_cur} (因子 1/{factor})')
        print(f'  positions.current_price: 待修复 {len(cur_fixes)} 行')

        # ---- 汇总 ----
        total = len(txn_fixes) + len(avg_fixes) + len(cur_fixes)
        if not args.apply:
            print(f'\n（dry-run）未做任何修改，共 {total} 处待修复。确认无误后加 --apply 执行；执行前会自动备份。')
            sys.exit(0)

        if total == 0:
            print('\n无需修复，数据已一致。')
            sys.exit(0)

        bak = _backup(path)
        print(f'\n  [OK] 已备份至 {bak}')
        for tid, _ttype, _old, new_price, *_ in txn_fixes:
            conn.execute('UPDATE transactions SET price=? WHERE id=?', (new_price, tid))
        for pid, _old, new_avg, *_ in avg_fixes:
            conn.execute('UPDATE positions SET avg_price=? WHERE id=?', (new_avg, pid))
        for pid, _ptype, _old, new_cur, _f in cur_fixes:
            conn.execute('UPDATE positions SET current_price=? WHERE id=?', (new_cur, pid))
        conn.commit()
        print(f'[OK] 价格缩放修复完成，共 {total} 处。')
    finally:
        conn.close()


if __name__ == '__main__':
    main()

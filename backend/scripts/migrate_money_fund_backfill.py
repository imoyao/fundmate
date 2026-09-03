# -*- coding: utf-8 -*-
"""#863 存量迁移：positions.is_money_fund 回填 + 孤儿货基流水挂回（口径 A）。

目标：让存量数据收敛到「写路径互斥」语义——货基持仓带正确 is_money_fund 标记，
且若同 (ledger_id, symbol) 存在孤儿货基本金流水（position_id IS NULL 且非收益行），
将其挂回该持仓，避免与持仓市值双计。

动作（默认 dry-run，仅打印 diff；--apply 才落库）：
1. 对 positions.type IN ('fund','money_fund') 逐行解析是否货币型（market 名录 + 代码段
   兜底，见 app/services/fund_utils.py），回填 is_money_fund；
2. 对 is_money_fund=True 的持仓，把同 (ledger, symbol) 的孤儿本金流水挂回 position_id
   （is_income 收益行不挂回，收益桶独立）。

用法（backend 目录）：
    pdm run python scripts/migrate_money_fund_backfill.py            # dry-run 打印 diff
    pdm run python scripts/migrate_money_fund_backfill.py --apply     # 执行写库
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resolve_db_paths() -> list[str]:
    db_url = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')
    if not db_url.startswith('sqlite'):
        print(f'仅支持 SQLite，DATABASE_URL={db_url}')
        sys.exit(1)
    path = db_url.replace('sqlite:///', '', 1).split('?', 1)[0]
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    paths = [path]
    alt = os.path.join(os.path.dirname(path), 'invest.user.dev.db')
    if os.path.exists(alt) and os.path.abspath(alt) != os.path.abspath(path):
        paths.append(alt)
    return paths


def _norm(symbol: str) -> str:
    s = (symbol or '').strip().upper()
    return s[2:] if s[:2] in ('SZ', 'SH') else s


def plan_for(path: str, money_fund_codes: dict[str, bool]):
    """计算待回填持仓与待挂回孤儿流水，不写库。"""
    conn = sqlite3.connect(path)
    try:
        tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
        if 'positions' not in tables or 'transactions' not in tables:
            return [], []
        rows = conn.execute(
            "SELECT id, ledger_id, symbol, type FROM positions WHERE type IN ('fund','money_fund')"
        ).fetchall()
        flag_updates = []
        for pid, lid, symbol, atype in rows:
            if not symbol:
                continue
            if atype == 'money_fund':
                resolved = True
            else:
                resolved = money_fund_codes.get(_norm(symbol))
                if resolved is None:
                    print(f'  [跳过] symbol {symbol} 未解析，保持原值')
                    continue
            flag_updates.append((pid, resolved))
        reattach_candidates = []
        for pid, flag in flag_updates:
            if not flag:
                continue
            row = conn.execute('SELECT ledger_id, symbol FROM positions WHERE id=?', (pid,)).fetchone()
            if not row or not row[0] or not row[1]:
                continue
            lid, symbol = row[0], row[1]
            cand = {_norm(symbol)} | {f'{p}{_norm(symbol)}' for p in ('SZ', 'SH')}
            placeholders = ','.join('?' * len(cand))
            orphans = conn.execute(
                'SELECT id FROM transactions WHERE ledger_id=? AND position_id IS NULL '
                "AND type IN ('money_fund','reverse_repo') AND COALESCE(is_income,0)=0 "
                f'AND symbol IN ({placeholders})',
                (lid, *sorted(cand)),
            ).fetchall()
            reattach_candidates.append((pid, [o[0] for o in orphans]))
        return flag_updates, reattach_candidates
    finally:
        conn.close()


def apply_for(path: str, flag_updates: list, reattach_candidates: list) -> None:
    conn = sqlite3.connect(path)
    try:
        for pid, flag in flag_updates:
            conn.execute('UPDATE positions SET is_money_fund=? WHERE id=?', (1 if flag else 0, pid))
        for pid, txn_ids in reattach_candidates:
            for tid in txn_ids:
                conn.execute('UPDATE transactions SET position_id=? WHERE id=?', (pid, tid))
        conn.commit()
    finally:
        conn.close()


def _collect_symbols(paths: list[str]) -> set[str]:
    symbols: set[str] = set()
    for p in paths:
        if not os.path.exists(p):
            continue
        conn = sqlite3.connect(p)
        try:
            for (sym,) in conn.execute("SELECT symbol FROM positions WHERE type IN ('fund','money_fund')").fetchall():
                if sym:
                    symbols.add(_norm(sym))
        finally:
            conn.close()
    return symbols


def main() -> None:
    parser = argparse.ArgumentParser(description='#863 存量货基回填/挂回迁移')
    parser.add_argument('--apply', action='store_true', help='真正执行写库；缺省为 dry-run')
    parser.add_argument('db', nargs='*', help='目标 SQLite 文件（缺省按 DATABASE_URL + invest.user.dev.db）')
    args = parser.parse_args()

    from app.services.fund_utils import resolve_money_fund_flags  # noqa: E402

    paths = args.db or _resolve_db_paths()
    codes = resolve_money_fund_flags(_collect_symbols(paths))

    for p in paths:
        print(f'==== 目标库: {p}')
        if not os.path.exists(p):
            print('  文件不存在，跳过')
            continue
        flag_updates, reattach_candidates = plan_for(p, codes)
        flag_true = sum(1 for _, f in flag_updates if f)
        flag_false = sum(1 for _, f in flag_updates if not f)
        orphan_total = sum(len(o) for _, o in reattach_candidates)
        print(f'  is_money_fund 待回填: {len(flag_updates)} 条（True={flag_true}, False={flag_false}）')
        print(f'  孤儿流水待挂回: {orphan_total} 条')
        if not args.apply:
            for pid, flag in flag_updates:
                print(f'    [pos {pid}] is_money_fund -> {bool(flag)}')
            for pid, txn_ids in reattach_candidates:
                if txn_ids:
                    print(f'    [pos {pid}] 挂回孤儿流水 {txn_ids}')
            continue
        apply_for(p, flag_updates, reattach_candidates)
        print('  [OK] 已执行写库')


if __name__ == '__main__':
    main()

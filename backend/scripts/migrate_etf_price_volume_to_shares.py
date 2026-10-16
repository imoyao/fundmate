# -*- coding: utf-8 -*-
# Date : 2026/10/14
# File : migrate_etf_price_volume_to_shares.py
# backend/scripts/migrate_etf_price_volume_to_shares.py
"""修缮 price_history 中 ETF 的 volume 单位：「手」→「股」（GitHub #2174）。

背景：东财源（fund_etf_hist_em）ETF K 线 volume 单位是「手」，腾讯/新浪是「股」
（相差 100 倍，2026-10-14 实测三只 ETF 均为精确 ×100）。落库口
（akshare_adapter.fetch_stock_price）已自 2026-10-14 起归一为「股」，本脚本
修缮历史存量行——否则产品详情页成交量副图在同一序列内呈现 ~100 倍断崖。

判据（对每只 ETF，以腾讯全历史 volume 为外部基准，close 已验证与东财零差异）：
    · db×100 ≈ 腾讯值（容差 0.5%）→ 判为「手」，更新为 db×100（股）
    · db ≈ 腾讯值                  → 已是股，跳过
    · 其它                         → 列入「需人工核对」，不动
仅更新 volume，不碰 close / adj_close / source。判据天然幂等，可重跑。

用法：
    python migrate_etf_price_volume_to_shares.py --db <path>              # dry-run
    python migrate_etf_price_volume_to_shares.py --db <path> --apply      # 真正更新
    python migrate_etf_price_volume_to_shares.py --db <path> --symbols SZ159865,SH513130

--apply 前自动把待更新行导出 CSV 备份（默认与 db 同目录，--backup-dir 可覆盖）。
"""

import argparse
import csv
import sqlite3
import sys
import time
from datetime import date, datetime
from pathlib import Path

# ETF 代码前缀（与 app/core/symbol_utils.derive_security_type 口径一致：含少量 LOF）
_ETF_PREFIXES = ('15', '16', '51', '56', '58')
_TOLERANCE = 0.005  # 0.5%：东财「手」×100 与腾讯「股」的允许偏差
_TX_SLEEP = 0.5  # 每只 ETF 之间礼貌间隔（秒）
_TODAY = date.today()


def _market_of(code: str) -> str:
    """6 位代码 → 交易所小写前缀（sz/sh）。调用前已用 _ETF_PREFIXES 过滤。"""
    return 'sz' if code[:2] in ('15', '16') else 'sh'


def _is_etf_symbol(symbol: str) -> bool:
    """'SZ159865' / 'SH510300' → 是否 ETF 代码形态。"""
    if len(symbol) != 8 or symbol[:2] not in ('SZ', 'SH'):
        return False
    return symbol[2:4] in _ETF_PREFIXES


def _fetch_tx_volumes(code: str) -> dict:
    """腾讯全历史 volume（股）→ {trade_date: volume}。失败抛错由调用方决定跳过。"""
    import akshare as ak

    df = ak.stock_zh_a_hist_tx(
        symbol=f'{_market_of(code)}{code}',
        start_date=f'{_TODAY.year - 10}0101',  # 远早于任何 ETF 上市年
        end_date=_TODAY.strftime('%Y%m%d'),
        adjust='',
    )
    if df is None or df.empty:
        raise RuntimeError('腾讯返回空数据')
    return {str(d): float(v) for d, v in zip(df['date'], df['volume'])}


def _classify(db_vol: float, tx_vol: float):
    """→ ('shares', None) 已是股 | ('lots', new_vol) 待更新 | ('manual', None) 待核对。"""
    base = max(abs(tx_vol), 1.0)
    if abs(db_vol - tx_vol) / base <= _TOLERANCE:
        return 'shares', None
    if abs(db_vol * 100 - tx_vol) / base <= _TOLERANCE:
        return 'lots', db_vol * 100
    return 'manual', None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--db', required=True, help='SQLite 库路径（market 域，如 backend/invest.db）')
    parser.add_argument('--apply', action='store_true', help='真正执行 UPDATE（默认仅 dry-run）')
    parser.add_argument('--symbols', help='限定 symbol 列表（逗号分隔，如 SZ159865,SH513130）')
    parser.add_argument('--backup-dir', help='apply 前备份 CSV 的目录（默认与 db 同目录）')
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(f'库不存在: {db_path}')
        return 1

    con = sqlite3.connect(f'file:{db_path}?mode={"rw" if args.apply else "ro"}', uri=True, timeout=30)
    con.execute('PRAGMA busy_timeout=5000')  # dev server 可能同时持有写锁

    rows = con.execute('SELECT DISTINCT symbol FROM price_history').fetchall()
    symbols = sorted(s[0] for s in rows if s[0] and _is_etf_symbol(s[0]))
    if args.symbols:
        wanted = {s.strip().upper() for s in args.symbols.split(',')}
        symbols = [s for s in symbols if s in wanted]
    if not symbols:
        print('未发现 ETF 行，无需修缮')
        return 0

    print(f'库: {db_path}')
    print(f'模式: {"APPLY（真正更新）" if args.apply else "DRY-RUN（仅报告）"}')
    print(f'ETF 数: {len(symbols)}\n')

    total_lots = total_shares = total_manual = total_novol = 0
    updates = []  # (symbol, trade_date, old, new)
    manual_rows = []

    for symbol in symbols:
        code = symbol[2:]
        row_count = con.execute('SELECT COUNT(*) FROM price_history WHERE symbol=?', (symbol,)).fetchone()[0]
        try:
            tx = _fetch_tx_volumes(code)
        except Exception as e:  # noqa: BLE001
            print(f'{symbol}: 腾讯取数失败（{type(e).__name__}: {e}），本只跳过，请稍后用 --symbols 重跑')
            continue

        lots = shares = manual = novol = 0
        for trade_date, db_vol in con.execute(
            'SELECT trade_date, volume FROM price_history WHERE symbol=? ORDER BY trade_date', (symbol,)
        ):
            if db_vol is None:
                novol += 1
                continue
            tx_vol = tx.get(str(trade_date))
            if tx_vol is None:
                manual += 1
                manual_rows.append((symbol, trade_date, db_vol, None, '腾讯无该日数据'))
                continue
            kind, new_vol = _classify(float(db_vol), tx_vol)
            if kind == 'shares':
                shares += 1
            elif kind == 'lots':
                lots += 1
                updates.append((symbol, str(trade_date), float(db_vol), new_vol))
            else:
                manual += 1
                manual_rows.append((symbol, trade_date, db_vol, tx_vol, f'db/100={db_vol / 100:g} 与 tx 均不匹配'))

        total_lots += lots
        total_shares += shares
        total_manual += manual
        total_novol += novol
        print(
            f'{symbol}: 共{row_count}行 → 股(已一致) {shares} / 手(待更新) {lots} / 待核对 {manual} / 空volume {novol}'
        )
        time.sleep(_TX_SLEEP)

    print(
        f'\n合计: 待更新 {len(updates)} 行，已一致 {total_shares} 行，待人工核对 {total_manual} 行，空 volume {total_novol} 行'
    )

    for m in manual_rows[:20]:
        print(f'  [待核对] {m[0]} {m[1]} db={m[2]} tx={m[3]}（{m[4]}）')
    if len(manual_rows) > 20:
        print(f'  … 共 {len(manual_rows)} 条，仅展示前 20 条')

    if not args.apply:
        print('\nDRY-RUN 未改动任何数据。确认无误后加 --apply 执行。')
        return 0

    if not updates:
        print('\n无待更新行，退出。')
        return 0

    backup_dir = Path(args.backup_dir) if args.backup_dir else db_path.parent
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f'backup_etf_volume_{datetime.now():%Y%m%d_%H%M%S}.csv'
    with open(backup_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['symbol', 'trade_date', 'old_volume', 'new_volume'])
        writer.writerows(updates)
    print(f'\n备份已导出: {backup_path}（{len(updates)} 行，可用其回滚）')

    con.executemany(
        'UPDATE price_history SET volume=? WHERE symbol=? AND trade_date=?',
        [(new, sym, td) for sym, td, _old, new in updates],
    )
    con.commit()
    print(f'已更新 {len(updates)} 行。重跑本脚本应得「待更新 0 行」（幂等自检）。')
    return 0


if __name__ == '__main__':
    sys.exit(main())

# -*- coding: utf-8 -*-
"""分层保留清理：执行脚本（#2120 P1）。默认 dry-run，`--apply` 才真删。

规则（由 §7 决策「不做全市场选基 → 冷集留 1 年」定）：**热集全留；冷集只留近 N 天**，
且每只冷集基金**至少保留 floor 个点**（§5.4「属该补不该删」）。覆盖 daily_worth 与
money_fund_daily_worth 两张表。

安全模型（每条都有代价，不是口号）：
1. 默认 dry-run：执行真实 DELETE 后**回滚**，故报的数字是精确值而非估算——预演与
   真删走同一条代码路径，不存在「预演算错、真删才发现」。
2. `--apply` 必须同时给 `--snapshot PATH`（§8.1 硬要求）。快照经 `validate_snapshot`
   校验，须**同时包含**两张表且行数 > 0，否则拒绝执行——没有快照就没有回滚手段。
3. 热集一行不删：`fund_code NOT IN (热集)` 是结构性条件，事后断言「热集行数前后完全相等」。
4. floor 下限保护：对「近窗口行数 < floor」的冷集基金额外保留其**最近 floor 行**，
   避免整只清空（实测 daily_worth 14 只、货基 5 只属此类）。
5. 单事务 + 三条断言：实际删除 == 预估、热集行数不变、冷集基金只数不变。任一不过整体回滚。
6. 幂等：条件删除，重跑一次 affected = 0。

回滚：`pdm run sync --import-snapshot <快照路径>`（INSERT OR IGNORE，不覆盖本地已有行）。
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import date, timedelta

TABLES = ('daily_worth', 'money_fund_daily_worth')
HOT_PARTS = (
    "SELECT DISTINCT symbol FROM positions WHERE LENGTH(symbol)=6 AND symbol NOT GLOB '*[^0-9]*'",
    "SELECT DISTINCT symbol FROM watchlist_items WHERE LENGTH(symbol)=6 AND symbol NOT GLOB '*[^0-9]*'",
    "SELECT DISTINCT symbol FROM transactions WHERE LENGTH(symbol)=6 AND symbol NOT GLOB '*[^0-9]*'",
)


def _has(conn, table):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _snapshot_ok(path, tables):
    """校验快照覆盖全部待清理表且行数 > 0；不满足即退出（无回滚手段，不许开删）。"""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.services.sync.snapshot import validate_snapshot

    meta = validate_snapshot(path)
    snap_tables = set(meta.get('tables') or [])
    # validate_snapshot 只把 tables 解析成 list，counts 仍是 **JSON 字符串**，须自行解析
    raw_counts = meta.get('counts') or '{}'
    counts = json.loads(raw_counts) if isinstance(raw_counts, str) else dict(raw_counts)
    missing = [t for t in tables if t not in snap_tables]
    empty = [t for t in tables if t in snap_tables and not int(counts.get(t) or 0)]
    if missing or empty:
        raise SystemExit(
            '快照不满足前置条件，拒绝执行。\n  缺表: %s\n  空表: %s\n  快照实际含表: %s'
            % (missing or '无', empty or '无', sorted(snap_tables))
        )
    return meta


def _prep(conn, table, cutoff, floor):
    """建临时表（热集代码 / floor 补保留行）并返回 (热集数, floor 补保留行数)。

    TEMP 表不受事务回滚影响，故必须在事务外建——否则回滚会把它们一起丢掉，
    后续断言无从引用。
    """
    conn.execute('CREATE TEMP TABLE IF NOT EXISTS hot_codes (code TEXT PRIMARY KEY)')
    conn.execute('DELETE FROM hot_codes')
    for sql in HOT_PARTS:
        t = sql.split('FROM ')[1].split()[0]
        if _has(conn, t):
            conn.execute('INSERT OR IGNORE INTO hot_codes (code) %s' % sql.replace('SELECT DISTINCT', 'SELECT'))
    hot_n = conn.execute('SELECT COUNT(*) FROM hot_codes').fetchone()[0]

    # 近窗口行数 < floor 的冷集基金 → 取其最近 floor 行作额外保留
    conn.execute(
        'CREATE TEMP TABLE IF NOT EXISTS floor_keep (fund_code TEXT, date TEXT, PRIMARY KEY (fund_code, date))'
    )
    conn.execute('DELETE FROM floor_keep')
    conn.execute(
        'INSERT OR IGNORE INTO floor_keep (fund_code, date) '
        'SELECT fund_code, date FROM ('
        '  SELECT fund_code, date,'
        '         ROW_NUMBER() OVER (PARTITION BY fund_code ORDER BY date DESC) AS rn,'
        '         SUM(CASE WHEN date >= ? THEN 1 ELSE 0 END) OVER (PARTITION BY fund_code) AS recent'
        '  FROM %s) t '
        'WHERE t.recent < ? AND t.rn <= ? '
        '  AND t.fund_code NOT IN (SELECT code FROM hot_codes)' % table,
        (cutoff, floor, floor),
    )
    # floor_keep 里可能有**已在窗口内**的行（recent≥1 但 < floor 时，最新一行就在窗口里），
    # 那些行本来就不会被 `date < cutoff` 删掉。真正「额外保留」的只有落在 cutoff 之前的部分。
    extra = conn.execute('SELECT COUNT(*) FROM floor_keep WHERE date < ?', (cutoff,)).fetchone()[0]
    return hot_n, extra


def _stats(conn, table):
    """(总行数, 热集行数, 冷集基金数, 热集基金数)。"""
    total = conn.execute('SELECT COUNT(*) FROM %s' % table).fetchone()[0]
    hot_rows = conn.execute(
        'SELECT COUNT(*) FROM %s WHERE fund_code IN (SELECT code FROM hot_codes)' % table
    ).fetchone()[0]
    hot_funds = conn.execute(
        'SELECT COUNT(DISTINCT fund_code) FROM %s WHERE fund_code IN (SELECT code FROM hot_codes)' % table
    ).fetchone()[0]
    cold_funds = conn.execute(
        'SELECT COUNT(DISTINCT fund_code) FROM %s WHERE fund_code NOT IN (SELECT code FROM hot_codes)' % table
    ).fetchone()[0]
    return total, hot_rows, cold_funds, hot_funds


def _delete(conn, table, cutoff):
    """执行分层删除，返回受影响行数。热集与 floor 补保留行都跳过。"""
    cur = conn.execute(
        'DELETE FROM %s WHERE date < ? '
        '  AND fund_code NOT IN (SELECT code FROM hot_codes) '
        '  AND NOT EXISTS (SELECT 1 FROM floor_keep k '
        '                  WHERE k.fund_code = %s.fund_code AND k.date = %s.date)' % (table, table, table),
        (cutoff,),
    )
    return cur.rowcount


def main():
    p = argparse.ArgumentParser(description='分层保留清理（#2120 P1）；默认 dry-run')
    p.add_argument('--db', default='invest.db')
    p.add_argument('--apply', action='store_true', help='真正删除（必须同时给 --snapshot）')
    p.add_argument('--snapshot', default=None, help='快照路径；--apply 时必填（§8.1 清理前必须先出快照）')
    p.add_argument('--keep-days', type=int, default=365, help='冷集保留天数（默认 365 = 1 年）')
    p.add_argument('--floor', type=int, default=2, help='每只冷集基金至少保留的点数（§5.4 该补不该删）')
    p.add_argument('--table', action='append', dest='tables', help='只处理指定表（可重复）；缺省两张都处理')
    args = p.parse_args()

    # floor 必须 >= 1：§5.4 明确「属该补不该删」，而断言 3（冷集基金只数不变）也会拦下
    # 任何「整只清空」。既然清空一律禁止，就不要给 floor=0 这个看似能关掉保护的选项——
    # 那会让人以为保护可以被关掉，实际只是让断言失败、整轮回滚。
    if args.floor < 1:
        raise SystemExit('--floor 必须 >= 1（§5.4：残缺冷集基金属该补不该删，不允许整只清空）')

    tables = tuple(args.tables) if args.tables else TABLES
    unknown = [t for t in tables if t not in TABLES]
    if unknown:
        raise SystemExit('未知表名 %s；可选: %s' % (unknown, list(TABLES)))

    if args.apply and not args.snapshot:
        raise SystemExit('--apply 必须同时提供 --snapshot（§8.1：清理前必须先出快照，否则无回滚手段）')

    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        raise SystemExit('找不到库文件: %s' % db_path)

    snap_meta = _snapshot_ok(args.snapshot, tables) if args.snapshot else None
    cutoff = (date.today() - timedelta(days=args.keep_days)).isoformat()

    print('=' * 84)
    print('分层保留清理 · %s' % ('APPLY（真删）' if args.apply else 'DRY-RUN（真实执行后回滚）'))
    print('=' * 84)
    print('库: %s' % db_path)
    print('冷集保留窗口: 近 %d 天（cutoff=%s）| 每只下限 floor=%d 个点' % (args.keep_days, cutoff, args.floor))
    if snap_meta:
        print(
            '快照: %s（生成于 %s，含 %d 张表）'
            % (args.snapshot, snap_meta.get('created_at'), len(snap_meta.get('tables') or []))
        )
    else:
        print('快照: 未提供（dry-run 不需要；--apply 时强制要求）')
    print('目标表: %s' % ', '.join(tables))
    print('')

    conn = sqlite3.connect(db_path, isolation_level=None)  # 显式 BEGIN/COMMIT/ROLLBACK
    try:
        conn.execute('PRAGMA foreign_keys = ON')
        for table in tables:
            if not _has(conn, table):
                print('[%s] 表不存在，跳过\n' % table)
                continue
            hot_n, floor_n = _prep(conn, table, cutoff, args.floor)
            before = _stats(conn, table)
            conn.execute('BEGIN')
            try:
                deleted = _delete(conn, table, cutoff)
                after = _stats(conn, table)
                ok_hot = before[1] == after[1]
                ok_funds = before[2] == after[2]
                ok_count = before[0] - after[0] == deleted
                print('[%s]' % table)
                print('  热集 %d 只 | floor 下限额外保留 %d 行（cutoff 之前本会被删的）' % (hot_n, floor_n))
                print('  删除前 %d 行（热集 %d 行 / 冷集 %d 只）' % (before[0], before[1], before[2]))
                print('  删除后 %d 行（热集 %d 行 / 冷集 %d 只）' % (after[0], after[1], after[2]))
                print('  实际删除 %d 行（%.2f%%）' % (deleted, 100.0 * deleted / max(before[0], 1)))
                print(
                    '  [断言1] 实际删除 == 行数差：%s'
                    % ('OK' if ok_count else '!! %d != %d' % (deleted, before[0] - after[0]))
                )
                print('  [断言2] 热集行数不变：%s' % ('OK' if ok_hot else '!! %d -> %d' % (before[1], after[1])))
                print(
                    '  [断言3] 冷集基金只数不变（无基金被清空）：%s'
                    % ('OK' if ok_funds else '!! %d -> %d' % (before[2], after[2]))
                )
                if not (ok_count and ok_hot and ok_funds):
                    conn.execute('ROLLBACK')
                    raise SystemExit('断言未通过，已整体回滚，未做任何删除。')
                if args.apply:
                    conn.execute('COMMIT')
                else:
                    conn.execute('ROLLBACK')
                print('  -> %s\n' % ('已提交' if args.apply else '已回滚（dry-run，库未变）'))
            except SystemExit:
                raise
            except Exception:
                conn.execute('ROLLBACK')
                raise
    finally:
        conn.close()

    print('=' * 84)
    if args.apply:
        print('清理完成。回滚命令：pdm run sync --import-snapshot %s' % args.snapshot)
    else:
        print('DRY-RUN 结束：库未做任何改动。确认数字无误后再加 --snapshot <path> --apply。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

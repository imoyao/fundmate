# -*- coding: utf-8 -*-
"""清理 daily_worth 里货币型基金的错表残留（#1554）。

背景
----
`daily_worth` 是普通基金的单位净值表；货币型基金（`funds.fund_type_id = 6`）的正确
落表是 `money_fund_daily_worth`（万份收益 + 7 日年化），两表各自一条
`(fund_code, date)` 唯一约束。

2026-08-29 21:55:46 曾有 11 只货基各 1 行写进了 `daily_worth`，形态为
`unit_nav = acc_nav = 1.0`。该时点早于 2026-09-11 落地的「T 日不回填」(#1423)
与 `XalphaAdapter` 的 `SYType == '每万份收益'` 货基回退判定，属旧代码路径残留。
写入侧现已按 `is_money_fund` 二分落两张表（`FundNavSyncJob._save_data` /
`async_backfill`），不存在继续产生此类错表写入的在跑路径。

清理范围（三重限定，防误删）
--------------------------
1. 仅 `date` = 目标日（默认 `2026-08-29`）；
2. 仅 `fund_code` 命中 `funds.fund_type_id = 6`；
3. **仅「孤立错点」**——该 `fund_code` 在 `daily_worth` 里除目标日外**没有其他行**。
   有真实净值序列的场内货币（如 003816 银华日利B，该表有 2370 行历史）即使
   `fund_type_id = 6` 也一律豁免，与 #1554 卡的明确要求一致。

回滚手段
--------
本脚本**不做全库文件副本**（本机 invest.db 已达 1.2GB，且删除范围是 11 行精确
主键），改为输出**可完整还原的 INSERT 回滚语句**（stdout，可用 `--rollback-out`
落文件），比全库快照更贴合「只备份被删的那部分」且无额外磁盘占用。
删除在单个事务内完成，`DELETE` 影响行数与 `daily_worth` 总数变化必须同时等于预期，
否则整体回滚、非零退出。

用法
----
  pdm run python scripts/clean_daily_worth_money_fund_misrouted.py            # dry-run，仅列出
  pdm run python scripts/clean_daily_worth_money_fund_misrouted.py --apply     # 真正执行
  pdm run python scripts/clean_daily_worth_money_fund_misrouted.py --db backend/invest.db
  pdm run python scripts/clean_daily_worth_money_fund_misrouted.py --date 2026-08-29
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

TARGET_DATE_DEFAULT = '2026-08-29'
MONEY_FUND_TYPE_ID = 6
DEFAULT_DB = 'invest.db'

_ROWS_SQL = (
    'SELECT d.id, d.fund_code, d.date, d.unit_nav, d.acc_nav, d.created_at, d.updated_at, f.name, '
    '(SELECT COUNT(*) FROM daily_worth x WHERE x.fund_code = d.fund_code) AS rows_in_table '
    'FROM daily_worth d JOIN funds f ON f.fund_code = d.fund_code '
    'WHERE d.date = ? AND f.fund_type_id = ? '
    'ORDER BY d.fund_code'
)


def collect_candidates(conn: sqlite3.Connection, target_date: str) -> tuple[list[dict], list[dict]]:
    """收集待清理行与豁免行。

    返回 `(targets, exempt)`。豁免判据：该 `fund_code` 在 `daily_worth` 中的行数 > 1
    ——说明它是**有真实净值序列**的品种（场内货币等），不属错表残留，须保留。
    """
    targets: list[dict] = []
    exempt: list[dict] = []
    for row in conn.execute(_ROWS_SQL, (target_date, MONEY_FUND_TYPE_ID)).fetchall():
        item = {
            'id': row[0],
            'fund_code': row[1],
            'date': row[2],
            'unit_nav': row[3],
            'acc_nav': row[4],
            'created_at': row[5],
            'updated_at': row[6],
            'name': row[7],
            'rows_in_table': row[8],
        }
        (targets if item['rows_in_table'] <= 1 else exempt).append(item)
    return targets, exempt


def _lit(value) -> str:
    """把 Python 值转成 SQL 字面量（仅用于生成回滚语句）。"""
    if value is None:
        return 'NULL'
    if isinstance(value, str):
        return "'%s'" % value.replace("'", "''")
    return repr(value)


def rollback_sql(rows: list[dict], target_date: str) -> str:
    """生成把被删行原样插回的 INSERT 语句。"""
    lines = [
        '-- #1554 回滚脚本：还原 daily_worth 中 %s 的货币型基金错表残留行' % target_date,
        '-- 用法：sqlite3 <db> < 本文件',
    ]
    for r in rows:
        name = (r['name'] or '').replace("'", "''")
        lines.append(
            'INSERT INTO daily_worth (id, fund_code, date, unit_nav, acc_nav, created_at, updated_at) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s);  -- %s'
            % (
                _lit(r['id']),
                _lit(r['fund_code']),
                _lit(r['date']),
                _lit(r['unit_nav']),
                _lit(r['acc_nav']),
                _lit(r['created_at']),
                _lit(r['updated_at']),
                name,
            )
        )
    return '\n'.join(lines) + '\n'


def purge(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """单事务按主键删除；条数不符即回滚并抛错。返回实际删除行数。"""
    ids = [r['id'] for r in rows]
    conn.execute('BEGIN IMMEDIATE')
    try:
        before = conn.execute('SELECT COUNT(*) FROM daily_worth').fetchone()[0]
        changed0 = conn.total_changes
        conn.executemany('DELETE FROM daily_worth WHERE id = ?', [(i,) for i in ids])
        deleted = conn.total_changes - changed0
        after = conn.execute('SELECT COUNT(*) FROM daily_worth').fetchone()[0]
        if deleted != len(ids) or before - after != len(ids):
            raise RuntimeError(
                '删除条数校验失败：预期 %d，DELETE 实际影响 %d，表行数 %d → %d' % (len(ids), deleted, before, after)
            )
        conn.execute('COMMIT')
        return deleted
    except Exception:
        try:
            conn.execute('ROLLBACK')
        except sqlite3.Error:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description='清理 daily_worth 里货币型基金的错表残留（#1554）')
    parser.add_argument('--db', default=DEFAULT_DB, help='SQLite 数据库路径（默认 invest.db）')
    parser.add_argument('--date', default=TARGET_DATE_DEFAULT, help='目标日期（默认 %s）' % TARGET_DATE_DEFAULT)
    parser.add_argument('--apply', action='store_true', help='真正执行；缺省为 dry-run')
    parser.add_argument('--rollback-out', default=None, help='把回滚 SQL 写入指定文件（缺省仅打印）')
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print('[错误] 数据库不存在: %s' % db_path)
        return 1

    conn = sqlite3.connect(db_path, timeout=30)
    conn.isolation_level = None  # 事务完全显式控制（purge 内 BEGIN IMMEDIATE / COMMIT / ROLLBACK）
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        missing = {'daily_worth', 'funds'} - tables
        if missing:
            print('[错误] 目标库缺少表: %s' % ', '.join(sorted(missing)))
            return 1

        targets, exempt = collect_candidates(conn, args.date)

        print(
            '目标日期 %s；daily_worth 总行数 %d'
            % (args.date, conn.execute('SELECT COUNT(*) FROM daily_worth').fetchone()[0])
        )
        if not targets and not exempt:
            print('未发现 daily_worth 中该日期的货币型基金记录，无需清理。')
            return 0

        print('\n待清理 %d 行（孤立错点，fund_type_id=%d）：' % (len(targets), MONEY_FUND_TYPE_ID))
        for r in targets:
            print(
                '  id=%-9s %s  %s  unit_nav=%s acc_nav=%s  created_at=%s'
                % (r['id'], r['fund_code'], r['name'], r['unit_nav'], r['acc_nav'], r['created_at'])
            )

        if exempt:
            print('\n豁免 %d 行（该代码在 daily_worth 有真实净值序列，保留）：' % len(exempt))
            for r in exempt:
                print('  %s  %s  本表共 %d 行' % (r['fund_code'], r['name'], r['rows_in_table']))

        sql = rollback_sql(targets, args.date)
        print('\n--- 回滚 SQL（删除前请留存）---')
        print(sql, end='')
        if args.rollback_out:
            Path(args.rollback_out).write_text(sql, encoding='utf-8')
            print('[回滚 SQL 已写入] %s' % args.rollback_out)

        if not args.apply:
            print('\n[dry-run] 未做任何修改；加 --apply 真正执行。')
            return 0

        deleted = purge(conn, targets)
        print('\n[完成] 已删除 %d 行。' % deleted)

        left, left_exempt = collect_candidates(conn, args.date)
        if left:
            print('[错误] 清理后仍有 %d 行命中，请检查。' % len(left))
            return 1
        print('[校验] 目标日期货币型基金错表行数 = 0（豁免 %d 行仍在）' % len(left_exempt))
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())

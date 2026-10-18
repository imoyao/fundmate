# -*- coding: utf-8 -*-
"""一次性修复：赎回费率阶梯里「逐字相同」的副本行与无人引用的重复规则行。

背景
----
用户报「赎回费率分布」弹窗里每档都显示两遍、且两行份额数一模一样
（2026-10-18）。逐层查下来是两条独立的成因，本脚本只处理其中「数据被复制」这条：

1. **数据层（本脚本处理）**：``fee_ratios`` 表**没有任何索引，也没有唯一约束**
   （实测该表在 ``sqlite_master`` 里的索引集为空），库里存在一次历史整表复制
   留下的**逐字相同**副本行——重复对的 ``rate`` / ``fee_amount`` / ``currency`` /
   ``created_at`` / ``updated_at`` **全同**（⇒ 复制，不是重新抓取后写入）；
   ``redeem_rules`` 同样每个 ``(start_day, end_day)`` 区间都有 2 行。
   读取侧逐行拼分布，于是每档输出两遍。

   本机实测（只读查询）：``fee_ratios`` 25,471 行 redeem，按
   ``(fund_code, fee_type, purchase_rule_id, redeem_rule_id, rate, fee_amount,
   currency)`` 分组有 12,732 组重复（每组 2 行）；``redeem_rules`` 248 行、
   去重后 124 个区间；没有任何 ``fee_ratios`` 指向那些「非最小 id 的重复规则」。

2. **解析层（由 PR #2331 及配套修复处理，本脚本不碰）**：天天基金费率页现在写的是
   「大于X，小于等于Y」且期限混用「年」，而旧解析只认「大于等于X，小于Y」，
   于是「大于30天，小于等于2年」被写成 ``(0, 2)``。本机有 245 只基金的阶梯在
   结构上已损坏（12 只同区间多行、7 只「年」被当「天」），那只基金的部分须由
   **重新同步费率**修复，不是删行能解决的。

判定口径（为什么分组键必须含 rate）
----------------------------------
同区间存在**两个不同费率**是解析缺陷的产物，但**不是重复行**：000513 / 000880 /
001827 三只基金的同区间各有两个费率（如 000513 的 0~7 天既有 1.5% 又有 0.75%）。
折叠它们等于替用户挑一个费率——**不可逆的数据损失**。故：
  · A 类分组键含 ``rate``：只有 (fund, type, rule, rate, fee_amount, currency)
    **完全一致**的行才算副本，费率不同的一律保留；
  · apply 后专门断言这三只基金的「同区间不同费率」行数与操作前一致。

修复动作（严格最小面）
--------------------
- A 类：删除重复副本行，每组保留 ``MIN(id)``；
- B 类：删除重复 ``redeem_rules`` 行，每区间保留 ``MIN(id)``，
  **仅当无 ``fee_ratios`` 引用时**；被引用的跳过并报告，不改指向、不强删；
- **不删任何费率行以外的表数据**，不改 ``rate`` 的值。

安全设计
--------
- **必须显式指定 ``--db``**：用标准库 ``sqlite3`` 直连给定文件，**不导入应用会话**
  ——避免环境里配了 ``SUPABASE_DATABASE_URL`` 时误连生产库。
- **默认 dry-run**：只打印将删除的行（按类别给出数量 + 样本）；写库需显式 ``--apply``。
- **apply 先备份**：把将删的行导出成可回放的 ``.sql``（逐行 ``INSERT``），
  默认写到库旁 ``data/backup_fee_ratio_dupes_<时间戳>.sql``，``--rollback-out`` 可改路径。
- **单事务 + 四重断言**，任一失败即整体回滚并非零退出：
  ① A 类重复组归零；② 无 ``fee_ratios`` 指向已删规则、无孤儿行；
  ③ ``redeem_rules`` 无重复区间；④ 三只歧义基金的同区间多费率行数与操作前一致。

用法
----
  cd backend
  python scripts/cleanup_fee_ratio_dupes.py --db invest.db            # dry-run
  python scripts/cleanup_fee_ratio_dupes.py --db invest.db --apply    # 写库（先自动备份）
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

#: 同一区间存在多个费率 = 真实歧义（解析缺陷产物），不是重复行。
#: 这三只基金的同区间多费率行数在 apply 前后必须一字不差（见断言④）。
AMBIGUOUS_FUNDS = ('000513', '000880', '001827')

FEE_RATIO_COLS = (
    'id',
    'fund_code',
    'fee_type',
    'rate',
    'fee_amount',
    'currency',
    'purchase_rule_id',
    'redeem_rule_id',
    'created_at',
    'updated_at',
)

#: 副本行判定键：缺一不可。rate 缺失会把「同区间不同费率」误判成重复（不可逆损失）。
DUPE_KEY = (
    'fund_code',
    'fee_type',
    'purchase_rule_id',
    'redeem_rule_id',
    'rate',
    'fee_amount',
    'currency',
)


def _conn(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def _match_clause(cols: tuple[str, ...], values: tuple) -> str:
    """按列值拼 WHERE 子句。

    **不能**写成 ``f'{c} IS {v!r}'``：``repr(None)`` 得到的是 Python 字面量
    ``None``，拼进 SQL 直接语法错误（NULL 必须显式写成 ``IS NULL``）。
    """
    parts = []
    for col, val in zip(cols, values):
        parts.append(f'{col} IS NULL' if val is None else f'{col} IS {val!r}')
    return ' AND '.join(parts)


def _fetch_duplicate_fee_ratios(conn: sqlite3.Connection) -> list[tuple[int, tuple]]:
    """返回 [(keep_id, (delete_id, ...)), ...]：逐字相同副本行，保留最小 id"""
    key_cols = ', '.join(DUPE_KEY)
    rows = conn.execute(
        f'SELECT {key_cols}, MIN(id), COUNT(*) FROM fee_ratios GROUP BY {key_cols} HAVING COUNT(*) > 1'
    ).fetchall()
    out = []
    for row in rows:
        keep_id = row[-2]
        ids = tuple(
            r[0]
            for r in conn.execute(
                f'SELECT id FROM fee_ratios WHERE {_match_clause(DUPE_KEY, row[:-2])} ORDER BY id'
            ).fetchall()
            if r[0] != keep_id
        )
        if ids:
            out.append((keep_id, ids))
    return out


def _fetch_duplicate_redeem_rules(conn: sqlite3.Connection) -> tuple[list[tuple[int, int]], list[int]]:
    """返回 (可删的重复规则 [(keep_id, delete_id)], 被引用因而跳过的 [rule_id])"""
    dupes = conn.execute(
        'SELECT start_day, end_day, MIN(id) FROM redeem_rules GROUP BY start_day, end_day HAVING COUNT(*) > 1'
    ).fetchall()
    deletable, referenced = [], []
    for _start, _end, keep_id in dupes:
        for (rule_id,) in conn.execute(
            'SELECT id FROM redeem_rules WHERE start_day IS ? AND end_day IS ? AND id != ? ORDER BY id',
            (_start, _end, keep_id),
        ).fetchall():
            used = conn.execute('SELECT COUNT(*) FROM fee_ratios WHERE redeem_rule_id = ?', (rule_id,)).fetchone()[0]
            if used:
                referenced.append(rule_id)
            else:
                deletable.append((keep_id, rule_id))
    return deletable, referenced


def _ambiguous_row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """三只歧义基金「同区间存在多个不同费率」的行数（apply 前后必须一致）"""
    out = {}
    for code in AMBIGUOUS_FUNDS:
        out[code] = conn.execute(
            """SELECT COUNT(*) FROM (
                   SELECT rr.start_day, rr.end_day
                   FROM fee_ratios fr JOIN redeem_rules rr ON fr.redeem_rule_id = rr.id
                   WHERE fr.fee_type = 'redeem' AND fr.fund_code = ?
                   GROUP BY rr.start_day, rr.end_day HAVING COUNT(DISTINCT fr.rate) > 1
               )""",
            (code,),
        ).fetchone()[0]
    return out


def _duplicate_group_count(conn: sqlite3.Connection) -> int:
    key_cols = ', '.join(DUPE_KEY)
    return conn.execute(
        f'SELECT COUNT(*) FROM (SELECT 1 FROM fee_ratios GROUP BY {key_cols} HAVING COUNT(*) > 1)'
    ).fetchone()[0]


def _duplicate_rule_range_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        'SELECT COUNT(*) FROM (SELECT 1 FROM redeem_rules GROUP BY start_day, end_day HAVING COUNT(*) > 1)'
    ).fetchone()[0]


def _orphan_fee_ratio_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        """SELECT COUNT(*) FROM fee_ratios fr
           LEFT JOIN redeem_rules rr ON fr.redeem_rule_id = rr.id
           WHERE fr.fee_type = 'redeem' AND rr.id IS NULL"""
    ).fetchone()[0]


def _write_backup(conn: sqlite3.Connection, dup_fee_ids: list[int], dup_rule_ids: list[int], out_path: Path) -> Path:
    """把将删的行导出成可回放的 INSERT 语句（逐行，含全部列）"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '-- fee_ratio_dupes 回滚脚本（按 id 原样回插）',
        f'-- 生成时间: {time.strftime("%Y-%m-%d %H:%M:%S")}',
        'BEGIN TRANSACTION;',
    ]
    for fid in dup_fee_ids:
        row = conn.execute(f'SELECT {", ".join(FEE_RATIO_COLS)} FROM fee_ratios WHERE id = ?', (fid,)).fetchone()
        if row:
            lines.append(_insert_stmt('fee_ratios', FEE_RATIO_COLS, row))
    for rid in dup_rule_ids:
        row = conn.execute(
            'SELECT id, start_day, end_day, created_at, updated_at FROM redeem_rules WHERE id = ?',
            (rid,),
        ).fetchone()
        if row:
            cols = ('id', 'start_day', 'end_day', 'created_at', 'updated_at')
            lines.append(_insert_stmt('redeem_rules', cols, row))
    lines.append('COMMIT;')
    out_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return out_path


def _insert_stmt(table: str, cols: tuple[str, ...], row: tuple) -> str:
    values = ', '.join('NULL' if v is None else str(v) for v in row)
    return f'INSERT INTO {table} ({", ".join(cols)}) VALUES ({values});'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='清理 fee_rates 逐字相同副本行与重复规则行')
    parser.add_argument('--db', required=True, help='SQLite 文件路径（不导入应用会话，避免误连生产）')
    parser.add_argument('--apply', action='store_true', help='真正写库（默认 dry-run）')
    parser.add_argument('--rollback-out', help='回滚 SQL 输出路径（默认写到库旁 data/ 目录）')
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f'找不到数据库文件: {db_path}', file=sys.stderr)
        return 2

    conn = _conn(db_path)
    try:
        dup_fees = _fetch_duplicate_fee_ratios(conn)
        dup_fee_ids = [fid for _keep, ids in dup_fees for fid in ids]
        dup_rules, referenced = _fetch_duplicate_redeem_rules(conn)
        dup_rule_ids = [rid for _keep, rid in dup_rules]
        ambiguous_before = _ambiguous_row_counts(conn)

        # 不能把上万个 id 拼进 IN(...): sqlite3 的变量数上限（旧版 999）会直接报错
        key_cols = ', '.join(DUPE_KEY)
        affected_funds = conn.execute(
            f'SELECT COUNT(DISTINCT fund_code) FROM ('
            f'SELECT fund_code FROM fee_ratios GROUP BY {key_cols} HAVING COUNT(*) > 1)'
        ).fetchone()[0]

        print('=' * 68)
        print('fee_ratios 副本行清理' + ('' if args.apply else '（dry-run，未写库）'))
        print('=' * 68)
        print(f'数据库          : {db_path}')
        print(f'A 类 重复副本行  : {len(dup_fee_ids)} 行，涉及 {affected_funds} 只基金')
        print(f'B 类 重复规则行  : {len(dup_rule_ids)} 行（无引用）')
        print(f'B 类 跳过        : {len(referenced)} 行（被 fee_ratios 引用，不强删）')
        print(f'歧义基金同区间多费率（必须保持不变）: {ambiguous_before}')
        if dup_fees:
            print('\n-- A 类样本（前 5 组）--')
            for keep_id, ids in dup_fees[:5]:
                row = conn.execute(
                    'SELECT fund_code, fee_type, rate, redeem_rule_id FROM fee_ratios WHERE id = ?',
                    (keep_id,),
                ).fetchone()
                print(f'  保留 id={keep_id} 删除 id={list(ids)}  fund={row[0]} rate={row[2]} rule={row[3]}')

        if not args.apply:
            print('\n[dry-run] 未写库。确认无误后加 --apply 执行（会自动先备份）。')
            return 0

        # ── apply：单事务 + 备份 + 四重断言 ──
        ts = time.strftime('%Y%m%d_%H%M%S')
        backup_path = (
            Path(args.rollback_out)
            if args.rollback_out
            else db_path.parent / 'data' / f'backup_fee_ratio_dupes_{ts}.sql'
        )
        _write_backup(conn, dup_fee_ids, dup_rule_ids, backup_path)
        print(f'\n回滚 SQL 已写出: {backup_path}')

        try:
            conn.execute('BEGIN')
            if dup_fee_ids:
                conn.executemany('DELETE FROM fee_ratios WHERE id = ?', [(i,) for i in dup_fee_ids])
            if dup_rule_ids:
                conn.executemany('DELETE FROM redeem_rules WHERE id = ?', [(i,) for i in dup_rule_ids])

            problems = []
            if _duplicate_group_count(conn) != 0:
                problems.append('A 类重复组未归零')
            if _orphan_fee_ratio_count(conn) != 0:
                problems.append('存在指向缺失规则的孤儿 fee_ratios')
            if _duplicate_rule_range_count(conn) != 0:
                problems.append('redeem_rules 仍有重复区间')
            if _ambiguous_row_counts(conn) != ambiguous_before:
                problems.append(f'歧义数据被误动: {ambiguous_before} -> {_ambiguous_row_counts(conn)}')
            if problems:
                conn.rollback()
                print('\n[FAIL] 断言未通过，已整体回滚: ' + '; '.join(problems), file=sys.stderr)
                return 1

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        print(f'[OK] 已删除副本行 {len(dup_fee_ids)} 条、重复规则行 {len(dup_rule_ids)} 条；四重断言全部通过')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())

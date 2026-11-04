# -*- coding: utf-8 -*-
"""把 ``ledgers.ledger_type`` 回填成「由 channel_category 派生」的结果（默认 dry-run）。

## 为什么会有这个脚本

``app/domains/ledgers/constants.py`` 的模块 docstring 是权威口径：

- ``channel_category``：用户可见的渠道分组（bank / securities / fund_platform / insurance /
  futures / other），账户列表分组、类型标签、排序、筛选**只读它**；
- ``ledger_type``：内部「资产类计算口径键」（stock / fund / bank / property / e_account /
  family），**只进计算 / 费率 / 视图分支逻辑**，且**由系统据 channel_category 派生**。

两者本应一致。但历史上有两条路径会写出矛盾的一对：

1. **旧版 E账户导入**（#2713 之前）：``_get_or_create_channel_ledger`` 新建账户时把
   ``ledger_type`` **写死 'fund'**，而同一个函数里的 ``channel_category`` 却正确地按
   机构 org_type 推导。于是银行渠道（浦发、招商…）被建成「自称基金、实为银行渠道」。
2. **用户改分组**：``channel_category`` 可编辑，而 ``ledger_type`` 在「账户带数据」时
   按设计不可变（改类型返回 409）。用户把某账户的渠道类别改成银行后，两者就此长期矛盾。

#2713 修掉了 ①（新建时派生、映射表补全 11 种 org_type、徽标改读 channel_category），
并把「同一销售机构只允许一个账户」的存量合并写成了 ``merge_institution_ledgers.py``；
但**存活账户的 ``ledger_type`` 没有回填**——``merge_institution_ledgers.py`` 只处理
「同机构多账户」的合并，不处理「单账户两字段矛盾」。

## 后果（为什么必须修，而不是「反正徽标已经读 channel_category 了」）

``LedgerService._apply_ledger_stats``（``app/services/ledger_service.py``）按
``ledger.ledger_type`` 分发统计口径：

- ``stock / fund / e_account`` → ``get_portfolio_stats``；
- ``bank`` → ``get_bank_stats`` + ``get_money_fund_stats``（现金余额、关联负债、货基占比）。

所以 ``ledger_type='fund'`` + ``channel_category='bank'`` 的账户会被当成基金账户渲染：
银行卡里的**现金不计入**、**关联房贷不出现在**该账户卡片、货基占比为 0。
徽标正确不代表口径正确——那是两个字段、两条读路径。

## 判据

- **派生结果只有一个来源**：``app.domains.ledgers.constants.map_channel_category_to_ledger_type``
  （禁止在本脚本里再写一份映射，否则又是「同一判据两处实现必然漂移」）。
- **``channel_category`` 为 NULL 的行一律跳过**：该函数对 None 返回 ``'bank'`` 属于
  「无信息时给个安全默认」，拿来回填等于凭默认值改用户数据。跳过并报告。
- **反向不唯一的渠道类别一律跳过**（实测踩到：``channel_category='other'`` 的
  「住房信息记录」``ledger_type='property'`` 会被推成 ``'bank'``）。原因是
  ``LEDGER_TYPE_TO_CHANNEL_CATEGORY_FALLBACK`` 是**多对一**的：``property`` /
  ``e_account`` / ``family`` 反推都落到 ``other``，正向再映射回来只能给个默认值。
  判据不写死 ``'other'``，而是从那张回退表**动态算出**所有「对应多个 ledger_type」
  的渠道类别——表变了判据跟着变，不靠人记得同步。
- **只改不一致的行**，且目标值必须落在模型允许的 ``ledger_type`` 枚举内；
  当前值不在枚举内的（脏数据 / 未知类型）同样跳过并报告，不猜。
- **幂等**：跑第二遍应当 0 候选。

## 安全设计

- **必须显式 ``--db``**：标准库 ``sqlite3`` 直连指定文件，**不导入应用会话**
  （避免环境里配了 ``SUPABASE_DATABASE_URL`` 时误连生产库）。
- **默认 dry-run**：只打印计划；写库需显式 ``--apply``。
- **apply 先把将被修改的整行 dump 成可回灌 SQL**（``--backup-out`` 可改路径），
  出问题直接 ``sqlite3 invest.db < backup.sql`` 回灌。
- **单事务 + 事后断言**：账户数 / 持仓 / 资产 / 流水 / 快照行数守恒、只改动计划内那几行、
  且除 ``ledger_type`` 外**逐列一致**、更新后重扫不再有候选；任一失败整体回滚并非零退出。

## 用法

.. code-block:: text

    cd backend
    python scripts/backfill_ledger_type_from_category.py --db invest.db              # dry-run
    python scripts/backfill_ledger_type_from_category.py --db invest.db --apply      # 真正写库

退出码：0 正常（含「无需修改」）；1 断言失败已回滚；2 输入不可用（库/表/映射拿不到）。
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.domains.ledgers.constants import (  # noqa: E402
    LEDGER_TYPE_TO_CHANNEL_CATEGORY_FALLBACK,
    map_channel_category_to_ledger_type,
)

# 模型定义的 ledger_type 枚举（见 app/domains/ledgers/models.py 的列注释）。
ALLOWED_LEDGER_TYPES = frozenset({'stock', 'fund', 'bank', 'property', 'e_account', 'family'})


def _ambiguous_channel_categories() -> frozenset:
    """反向对应多个 ``ledger_type`` 的渠道类别——正向映射对它们只能是默认值，不可回填。

    由 ``LEDGER_TYPE_TO_CHANNEL_CATEGORY_FALLBACK`` 现算，不写死名单：
    当前 ``other`` ← {property, e_account, family} 三个，故只有它被判为不唯一；
    ``bank`` ← {bank}、``securities`` ← {stock}、``fund_platform`` ← {fund} 都是唯一的。
    """
    reverse: Dict[str, set] = {}
    for ledger_type, category in LEDGER_TYPE_TO_CHANNEL_CATEGORY_FALLBACK.items():
        reverse.setdefault(category, set()).add(ledger_type)
    return frozenset(c for c, types in reverse.items() if len(types) > 1)


AMBIGUOUS_CHANNEL_CATEGORIES = _ambiguous_channel_categories()

# 应用户数据改动时必须守恒的表（只改 ledgers 一列，其余表一行都不该动）。
CONSERVED_TABLES = (
    'positions',
    'assets',
    'transactions',
    'asset_snapshots',
    'pnl_daily_snapshots',
    'position_import_meta',
)

# 只改这一列；断言时据此逐列比对「除它之外完全一致」。
MUTABLE_COLUMN = 'ledger_type'


@dataclass
class Plan:
    """待修改清单与跳过清单（跳过也必须报出来，否则「悄悄没修」看不出来）。"""

    changes: List[Dict[str, object]] = field(default_factory=list)
    skipped: List[Tuple[Dict[str, object], str]] = field(default_factory=list)


def _rows(conn: sqlite3.Connection, sql: str, params: Tuple[object, ...] = ()) -> List[sqlite3.Row]:
    """按行取（用独立 cursor 设 row_factory，不改调用方连接的状态）。"""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    try:
        return list(cursor.execute(sql, params))
    finally:
        cursor.close()


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    """行数。表不存在直接抛——「拿不到输入」不得退化成 0（空 ≠ 没拿到）。"""
    try:
        return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    except sqlite3.OperationalError as exc:  # pragma: no cover - 只在库结构异常时触发
        raise SystemExit(f'致命：读不到表 {table}（{exc}）——结论不可信，已中止') from exc


def plan(conn: sqlite3.Connection) -> Plan:
    """算出 ``ledger_type`` 与 ``channel_category`` 派生结果不一致的账户。"""
    result = Plan()
    for row in _rows(
        conn,
        'SELECT * FROM ledgers WHERE channel_category IS NOT NULL ORDER BY id',
    ):
        record = dict(row)
        current = (record.get(MUTABLE_COLUMN) or '').strip()
        category = (record.get('channel_category') or '').strip()
        if category in AMBIGUOUS_CHANNEL_CATEGORIES:
            expected = map_channel_category_to_ledger_type(category)
            if current != expected:
                result.skipped.append(
                    (
                        record,
                        f'channel_category={category!r} 反向对应多个 ledger_type，'
                        f'派生值 {expected!r} 只是默认值，不足以定 {current!r}',
                    )
                )
            continue
        expected = map_channel_category_to_ledger_type(category)
        if current == expected:
            continue
        if current not in ALLOWED_LEDGER_TYPES:
            result.skipped.append((record, f'当前 ledger_type={current!r} 不在允许集合内'))
            continue
        if expected not in ALLOWED_LEDGER_TYPES:  # pragma: no cover - 映射表恒定输出枚举内值
            result.skipped.append((record, f'派生结果 {expected!r} 不在允许集合内'))
            continue
        record['_expected'] = expected
        result.changes.append(record)
    return result


def dump_rows(rows: List[Dict[str, object]], columns: List[str]) -> str:
    """把整行导出成可回灌的 INSERT（回灌前先 DELETE 同 id，避免主键冲突）。"""
    lines = [
        '-- 回灌：sqlite3 <db> < 本文件',
        'PRAGMA foreign_keys=OFF;',
        'BEGIN;',
    ]
    for row in rows:
        values = []
        for col in columns:
            value = row[col]
            if value is None:
                values.append('NULL')
            elif isinstance(value, (int, float)):
                values.append(repr(value))
            else:
                text = str(value).replace("'", "''")
                values.append(f"'{text}'")
        lines.append(f'DELETE FROM ledgers WHERE id = {row["id"]};')
        lines.append(f'INSERT INTO ledgers ({", ".join(columns)}) VALUES ({", ".join(values)});')
    lines.append('COMMIT;')
    return '\n'.join(lines) + '\n'


def apply_plan(conn: sqlite3.Connection, p: Plan, backup_path: Path) -> None:
    """单事务改库；任一断言失败整体回滚。"""
    if not p.changes:
        print('无需修改：所有账户的 ledger_type 已与 channel_category 一致。')
        return

    columns = [c[1] for c in conn.execute('PRAGMA table_info(ledgers)')]

    # 计划完整性先验：目标值必须真是「按 channel_category 派生」得到的
    # （防止调用方手搓 plan 把错误值带进来；断言 3 只能发现「没收敛」，发现不了「改成另一个错值」）。
    for change in p.changes:
        derived = map_channel_category_to_ledger_type(str(change.get('channel_category') or ''))
        if change['_expected'] != derived:
            raise AssertionError(
                f'计划内 #{change["id"]} 的目标值 {change["_expected"]!r} 不是派生结果 {derived!r}，拒绝执行'
            )

    before_counts = {t: _table_count(conn, t) for t in CONSERVED_TABLES}
    before_ledgers = _table_count(conn, 'ledgers')
    before_rows = {int(c['id']): dict(c) for c in p.changes}

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(dump_rows(list(p.changes), columns), encoding='utf-8', newline='\n')
    print(f'回灌脚本：{backup_path}')

    try:
        with conn:
            for change in p.changes:
                conn.execute(
                    'UPDATE ledgers SET ledger_type = ? WHERE id = ?',
                    (change['_expected'], change['id']),
                )

            # ── 断言 1：只改动计划内的行，且除 ledger_type 外逐列一致 ──
            for ledger_id, old in before_rows.items():
                now = dict(_rows(conn, 'SELECT * FROM ledgers WHERE id = ?', (ledger_id,))[0])
                if now[MUTABLE_COLUMN] != old['_expected']:
                    raise AssertionError(f'账户 {ledger_id} 的 ledger_type 未落成 {old["_expected"]!r}')
                for col in columns:
                    if col == MUTABLE_COLUMN:
                        continue
                    if now[col] != old[col]:
                        raise AssertionError(f'账户 {ledger_id} 的 {col} 被意外改动：{old[col]!r} → {now[col]!r}')

            # ── 断言 2：其余表一行不动（只改了一列，不该有连带写入）──
            for table, expected in before_counts.items():
                actual = _table_count(conn, table)
                if actual != expected:
                    raise AssertionError(f'{table} 行数变化：{expected} → {actual}')
            if _table_count(conn, 'ledgers') != before_ledgers:
                raise AssertionError('ledgers 行数变化')

            # ── 断言 3：重扫不再有候选（幂等 + 判据真的收敛了）──
            # 只问一次：先看有冲突再问一遍输出，是「同一事实问两次」的经典坑
            # （第二次的输出与第一次的退出码对不上时，结论会静默取反）。
            after = plan(conn)
            if after.changes:
                raise AssertionError(f'重扫仍有候选，说明判据未收敛：{[c["id"] for c in after.changes]}')
    except Exception:
        print('❌ 断言失败，已整体回滚（库未改动）。')
        raise

    print(f'✅ 已提交：{len(p.changes)} 个账户的 ledger_type 回填为派生值。')


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='按 channel_category 回填 ledgers.ledger_type（默认 dry-run）')
    parser.add_argument('--db', required=True, help='invest.db 路径（必填，避免误连生产库）')
    parser.add_argument('--apply', action='store_true', help='真正写库（默认仅打印计划）')
    parser.add_argument('--backup-out', default=None, help='回灌 SQL 输出路径（默认库旁 data/）')
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f'致命：找不到数据库 {db_path}')
        return 2

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        p = plan(conn)
        print(f'候选：{len(p.changes)} 个账户；跳过：{len(p.skipped)} 个')
        for change in p.changes:
            print(
                f'  #{change["id"]:<4} {change["name"]:<22} '
                f'channel_category={change["channel_category"]:<14} '
                f'ledger_type {change["ledger_type"]} → {change["_expected"]}'
            )
        for record, reason in p.skipped:
            print(f'  跳过 #{record["id"]} {record["name"]}：{reason}')

        if not args.apply:
            print('\n（dry-run，未写库；确认无误后加 --apply）')
            return 0

        backup = (
            Path(args.backup_out)
            if args.backup_out
            else db_path.parent / 'data' / f'backup_ledger_type_{datetime.now():%Y%m%d_%H%M%S}.sql'
        )
        apply_plan(conn, p, backup)
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())

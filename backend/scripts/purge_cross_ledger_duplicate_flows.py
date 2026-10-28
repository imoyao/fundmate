# -*- coding: utf-8 -*-
"""清理「同一份交割单被导入到两个账本」产生的流水副本（默认 dry-run）。

## 为什么会有这个脚本

2026-10-28 排查「微众银行账户为什么多出 50 万账外货基」时发现：``ledger 3``（微众银行）
的 416 笔流水里 **415 笔是 ``ledger 12``（同花顺/银河证券）交割单的副本**。

判据是 ``import_hash``：408 个 hash 在两个账本各存一份，逐笔日期/金额/类型一致；
其中 251 笔是 **SH 可转债**——银行渠道不可能有可转债交易，只可能来自证券账户。

时间线：

    2026-06-16  ledger 3 导入 415 笔银河交割单      ← 导错目标账本
    2026-08-16  创建 ledger 12（同花顺/银河）        ← 正确的账本
    2026-08-29  ledger 12 全量重导 1,211 笔         ← 权威副本在这里

放行它的是 #1076「现金/货基跨账本重导兼容」：去重作用域从全局降为
``(ledger_id, import_hash)``（#1065/#1020）。那个设计的假设是「用户**故意**把同一份
交割单导进两个账本」（券商账户与现金账户分开记账），没有覆盖「**导错**账本」这一种。

## 判据（宁可留多，不可删错）

- 待删集合 = ``from_ledger`` 中 ``import_hash`` **同时出现在 keep_ledger** 的行。
  跨账本同 hash 是必要条件；同账本内的重复不在本脚本范围内。
- **任何一行带 ``position_id`` 或 ``link_group_id`` 就整批拒绝执行**：那说明它已经是
  持仓的锚点或配对组的一半，删掉会让持仓失去落点。本项目历史上已经因为
  「清仓删持仓行导致锚点丢失」吃过一次亏。
- ``entry_status='pending_cash'`` 的行同样拒绝——它们还没决定归属。

## 安全设计

- **必须显式 ``--db``**：用标准库 ``sqlite3`` 直连指定文件，**不导入应用会话**
  ——避免环境里配了 ``SUPABASE_DATABASE_URL`` 时误连生产库。
- **默认 dry-run**：只打印计划；写库需显式 ``--apply``。
- ``--apply`` 先整库备份（``Connection.backup()``，``cp`` 会漏掉 WAL 里的改动），
  再单事务执行，最后断言行数守恒。

## 用法

    python scripts/purge_cross_ledger_duplicate_flows.py --db invest.db \
        --from-ledger 3 --keep-ledger 12            # 看计划

    python scripts/purge_cross_ledger_duplicate_flows.py --db invest.db \
        --from-ledger 3 --keep-ledger 12 --apply    # 真删
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# 拒绝执行的行特征：这些字段非空即为「已挂载」，不能随副本一起删
_FORBIDDEN_ANCHORS = ('position_id', 'link_group_id')


def _cross_ledger_hashes(con: sqlite3.Connection, from_ledger: int, keep_ledger: int) -> list[str]:
    """两账本共用的 import_hash（跨账本副本的判定键）。"""
    rows = con.execute(
        """
        SELECT a.import_hash
        FROM transactions a
        JOIN transactions b
          ON a.import_hash = b.import_hash
         AND b.ledger_id = ?
        WHERE a.ledger_id = ?
          AND a.import_hash IS NOT NULL
        GROUP BY a.import_hash
        """,
        (keep_ledger, from_ledger),
    ).fetchall()
    return [r[0] for r in rows]


def _collect_targets(con: sqlite3.Connection, from_ledger: int, hashes: list[str]) -> list[sqlite3.Row]:
    if not hashes:
        return []
    marks = ','.join('?' * len(hashes))
    return con.execute(
        f"""
        SELECT id, type, trade_date, amount, asset_type, symbol, position_name,
               position_id, link_group_id, entry_status, import_hash, is_income
        FROM transactions
        WHERE ledger_id = ? AND import_hash IN ({marks})
        ORDER BY id
        """,
        (from_ledger, *hashes),
    ).fetchall()


def _ledger_snapshot(con: sqlite3.Connection, ledger_id: int) -> dict:
    """账本的流水条数 / 孤儿货基净额（分）/ 持仓条数，用于前后对比。"""
    txn_count = con.execute('SELECT COUNT(*) FROM transactions WHERE ledger_id = ?', (ledger_id,)).fetchone()[0]
    orphan_net = con.execute(
        """
        SELECT COALESCE(SUM(
            CASE WHEN type IN ('buy','deposit') THEN amount
                 WHEN type IN ('sell','withdraw') THEN -amount
                 ELSE 0 END), 0)
        FROM transactions
        WHERE ledger_id = ? AND position_id IS NULL
          AND asset_type IN ('money_fund','reverse_repo')
          AND COALESCE(is_income, 0) = 0
        """,
        (ledger_id,),
    ).fetchone()[0]
    pos_count = con.execute('SELECT COUNT(*) FROM positions WHERE ledger_id = ?', (ledger_id,)).fetchone()[0]
    return {'txn': txn_count, 'orphan_net_cents': orphan_net, 'positions': pos_count}


def _yuan(cents: int) -> str:
    return f'{cents / 100.0:,.2f}'


def main() -> int:
    ap = argparse.ArgumentParser(description='清理跨账本重复导入产生的流水副本')
    ap.add_argument('--db', required=True, help='SQLite 文件路径（必须显式指定）')
    ap.add_argument('--from-ledger', type=int, required=True, help='删哪一侧的副本')
    ap.add_argument('--keep-ledger', type=int, required=True, help='以哪个账本为权威副本')
    ap.add_argument('--apply', action='store_true', help='真正写库（默认只打印计划）')
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f'[FATAL] 数据库不存在: {db_path}', file=sys.stderr)
        return 2

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    try:
        names = {
            r[0]: r[1]
            for r in con.execute(
                'SELECT id, name FROM ledgers WHERE id IN (?, ?)', (args.from_ledger, args.keep_ledger)
            )
        }
        for lid in (args.from_ledger, args.keep_ledger):
            if lid not in names:
                print(f'[FATAL] 账本 {lid} 不存在', file=sys.stderr)
                return 2
        print(f'删除侧 ledger {args.from_ledger}: {names[args.from_ledger]}')
        print(f'保留侧 ledger {args.keep_ledger}: {names[args.keep_ledger]}')

        hashes = _cross_ledger_hashes(con, args.from_ledger, args.keep_ledger)
        targets = _collect_targets(con, args.from_ledger, hashes)

        print(f'\n共用 import_hash: {len(hashes)} 个')
        print(f'命中待删流水: {len(targets)} 笔')
        if not targets:
            print('没有需要清理的行，结束。')
            return 0

        # ── 拒绝条件 ────────────────────────────────────────────────
        blocked: list[str] = []
        for field in _FORBIDDEN_ANCHORS:
            bad = [t['id'] for t in targets if t[field] is not None]
            if bad:
                blocked.append(f'{field} 非空 {len(bad)} 笔（如 {bad[:5]}）')
        pending = [t['id'] for t in targets if t['entry_status'] == 'pending_cash']
        if pending:
            blocked.append(f"entry_status='pending_cash' {len(pending)} 笔（如 {pending[:5]}）")
        if blocked:
            print('\n[FATAL] 待删集合含已挂载行，整批拒绝执行：', file=sys.stderr)
            for b in blocked:
                print(f'  - {b}', file=sys.stderr)
            return 3

        # ── 计划明细 ────────────────────────────────────────────────
        by_type: dict[tuple[str, str], list[int]] = {}
        for t in targets:
            key = (t['asset_type'] or '(null)', t['type'])
            by_type.setdefault(key, []).append(t['id'])
        print('\n构成（asset_type / type → 笔数）:')
        for (at, tp), ids in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
            print(f'  {at:<12} {tp:<14} {len(ids):>4} 笔')

        # 孤儿货基净额：判据必须与 _ledger_snapshot 的 SQL **逐字一致**
        # （asset_type / position_id IS NULL / is_income 三态 / 只认 buy·deposit·sell·withdraw），
        # 否则下面那条「删除后净额 == 预期」的断言会拿两个不同口径相减，红得没有意义。
        # 第一版就是漏了 dividend_cash（12 笔 81.74 元），净额算成 505,939.35。
        orphan_cents = 0
        for t in targets:
            if t['asset_type'] not in ('money_fund', 'reverse_repo') or t['is_income']:
                continue
            if t['type'] in ('buy', 'deposit'):
                orphan_cents += t['amount']
            elif t['type'] in ('sell', 'withdraw'):
                orphan_cents -= t['amount']
        print(f'\n其中孤儿货基/逆回购净额: {_yuan(orphan_cents)} 元（这部分计入家庭总资产）')

        before_from = _ledger_snapshot(con, args.from_ledger)
        before_keep = _ledger_snapshot(con, args.keep_ledger)
        total_before = con.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]

        print('\n删除前:')
        print(
            f'  ledger {args.from_ledger}: 流水 {before_from["txn"]} 笔 / '
            f'孤儿净额 {_yuan(before_from["orphan_net_cents"])} 元 / 持仓 {before_from["positions"]} 行'
        )
        print(
            f'  ledger {args.keep_ledger}: 流水 {before_keep["txn"]} 笔 / '
            f'孤儿净额 {_yuan(before_keep["orphan_net_cents"])} 元 / 持仓 {before_keep["positions"]} 行'
        )
        print(f'  transactions 全表: {total_before} 笔')

        if not args.apply:
            print('\n[dry-run] 未写库。加 --apply 执行。')
            return 0

        # ── 备份 ────────────────────────────────────────────────────
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup_path = db_path.with_name(f'{db_path.name}.bak-{stamp}-purge')
        dst = sqlite3.connect(str(backup_path))
        try:
            con.backup(dst)  # WAL 里的改动一并落进备份
        finally:
            dst.close()
        print(f'\n已备份: {backup_path} ({backup_path.stat().st_size:,} B)')

        # ── 单事务删除 ──────────────────────────────────────────────
        ids = [t['id'] for t in targets]
        marks = ','.join('?' * len(ids))
        try:
            con.execute('BEGIN IMMEDIATE')
            cur = con.execute(f'DELETE FROM transactions WHERE id IN ({marks})', ids)
            deleted = cur.rowcount
            if deleted != len(ids):
                raise RuntimeError(f'删除行数不符: 预期 {len(ids)}，实际 {deleted}')
            con.commit()
        except Exception as exc:  # noqa: BLE001 - 任何异常都必须整体回滚
            con.rollback()
            print(f'[FATAL] 删除失败已回滚: {exc}', file=sys.stderr)
            return 4

        # ── 守恒断言 ────────────────────────────────────────────────
        after_from = _ledger_snapshot(con, args.from_ledger)
        after_keep = _ledger_snapshot(con, args.keep_ledger)
        total_after = con.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]

        checks = [
            ('删除行数 == 计划笔数', deleted == len(ids), f'{deleted} vs {len(ids)}'),
            (
                '删除侧流水减少量 == 删除行数',
                before_from['txn'] - after_from['txn'] == deleted,
                f'{before_from["txn"]} - {after_from["txn"]} != {deleted}',
            ),
            (
                '保留侧流水条数不变',
                before_keep['txn'] == after_keep['txn'],
                f'{before_keep["txn"]} -> {after_keep["txn"]}',
            ),
            ('全表行数守恒', total_before - total_after == deleted, f'{total_before} -> {total_after}'),
            (
                '删除侧持仓行数不变',
                before_from['positions'] == after_from['positions'],
                f'{before_from["positions"]} -> {after_from["positions"]}',
            ),
        ]
        # 孤儿净额必须正好减去上面算出的金额（这一条直接对应家庭总资产的变化）
        expected_orphan = before_from['orphan_net_cents'] - orphan_cents
        checks.append(
            (
                '删除侧孤儿净额 == 预期',
                after_from['orphan_net_cents'] == expected_orphan,
                f'{_yuan(after_from["orphan_net_cents"])} vs {_yuan(expected_orphan)}',
            )
        )

        print('\n删除后:')
        print(
            f'  ledger {args.from_ledger}: 流水 {after_from["txn"]} 笔 / '
            f'孤儿净额 {_yuan(after_from["orphan_net_cents"])} 元 / 持仓 {after_from["positions"]} 行'
        )
        print(
            f'  ledger {args.keep_ledger}: 流水 {after_keep["txn"]} 笔 / '
            f'孤儿净额 {_yuan(after_keep["orphan_net_cents"])} 元 / 持仓 {after_keep["positions"]} 行'
        )
        print(f'  transactions 全表: {total_after} 笔')

        print('\n断言:')
        failed = 0
        for label, ok, detail in checks:
            print(f'  [{"PASS" if ok else "FAIL"}] {label}' + ('' if ok else f' ({detail})'))
            if not ok:
                failed += 1
        if failed:
            print(f'\n[FATAL] {failed} 条断言失败——数据已写入，请用上面的备份回滚。', file=sys.stderr)
            return 5
        print('\n完成。')
        return 0
    finally:
        con.close()


if __name__ == '__main__':
    sys.exit(main())

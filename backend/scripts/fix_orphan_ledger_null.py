# -*- coding: utf-8 -*-
"""修复存量脏数据：账本引用悬空的流水按 ``account_name`` 归属回填（#2875）。

背景
----
真实库曾有 **26 笔**存量 NULL 行（25 笔 dividend_tax + 1 笔 bond_redeem，来自
2026-11-02/03 两次导入的 TAX 分支漏传），它们不进任何账本视图，只能全表扫描发现。
另有一类形态：``ledger_id`` 指向**已删除账本**（SQLite 在 ``PRAGMA foreign_keys=OFF``
下 FK 不生效，迁移脚本大量在该模式下重建表），同样不进账本视图。

写入侧现由 ``TransactionService.create`` 校验「非空 id 必须存在且属于本家庭」——
#2875 撤掉的只是「NULL 即报错」的硬拦（手工建仓 / 探市的 NULL 合法）。新脏数据
被堵住，存量两类仍需本脚本回填。

归属规则（保守，宁缺毋滥）
--------------------------
- 只处理 ``position_id IS NULL`` 的行；挂了持仓的行由账户管理页「未归置数据」
  连持仓一起归入，单笔按 account_name 猜账本反而可能把流水与所属持仓拆开；
- ``ledger_id`` 为 NULL **或** 指向已删除账本（``NOT IN (SELECT id FROM ledgers)``）
  都算悬空，两类一起盘点、一起回填；
- ``account_name`` 非空，且在**同 family** 下恰好有一条 ``ledgers.name`` 精确同名
  （区分大小写、不做模糊/去空格猜测）⇒ 回填该 ledger；
- account_name 为空 / 无匹配 / 同 family 同名多条（歧义）⇒ 列出来跳过，人工处理。

默认**只读预览**；``--apply`` 才写库。回填前打印每一行的修改前后值；
回填后自校验（剩余悬空计数）。WHERE 条件仍判「当前仍悬空」，重复执行幂等，
并发下也不会覆盖别人刚归好的账本。

用法
----
  pdm run python scripts/fix_orphan_ledger_null.py                # 预览
  pdm run python scripts/fix_orphan_ledger_null.py --db backend/invest.db --apply
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB = 'invest.db'

# 账本引用悬空的唯一判据（不带表别名，供候选查询 / UPDATE / 自校验复用）。
_DANGLING_LEDGER = '(ledger_id IS NULL OR ledger_id NOT IN (SELECT id FROM ledgers))'

_CANDIDATE_SQL = (
    'SELECT id, family_id, type, symbol, account_name, amount, '
    '       substr(created_at, 1, 10) '
    'FROM transactions '
    'WHERE ' + _DANGLING_LEDGER + ' AND position_id IS NULL '
    'ORDER BY created_at, id'
)


def resolve_ledger(conn: sqlite3.Connection, family_id: int | None, account_name: str | None) -> tuple[int | None, str]:
    """按 ``(family_id, name)`` 精确匹配唯一账本；返回 (ledger_id, 不可回填原因)。

    匹配不上时 ``ledger_id`` 为 None，原因为空串表示「没有 account_name」。
    """
    name = (account_name or '').strip()
    if not name:
        return None, 'account_name 为空，无法归属'
    rows = conn.execute('SELECT id FROM ledgers WHERE family_id = ? AND name = ?', (family_id, name)).fetchall()
    if not rows:
        return None, f'同 family 下无名为 {name!r} 的账本'
    if len(rows) > 1:
        return None, f'同 family 下有 {len(rows)} 个同名账本，歧义'
    return rows[0][0], ''


def plan_fixes(conn: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
    """返回 (可回填清单, 需人工清单)。只读。"""
    fixable, manual = [], []
    for tid, family_id, ttype, symbol, account_name, amount, created in conn.execute(_CANDIDATE_SQL):
        ledger_id, reason = resolve_ledger(conn, family_id, account_name)
        row = {
            'id': tid,
            'family_id': family_id,
            'type': ttype,
            'symbol': symbol,
            'account_name': account_name,
            'amount': amount,
            'created': created,
            'ledger_id': ledger_id,
            'reason': reason,
        }
        (fixable if ledger_id is not None else manual).append(row)
    return fixable, manual


def apply_fixes(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """回填 ledger_id。调用方负责开事务与提交；返回实际修改行数。"""
    changed = 0
    for r in rows:
        cur = conn.execute(
            'UPDATE transactions SET ledger_id = ? WHERE id = ? AND ' + _DANGLING_LEDGER,
            (r['ledger_id'], r['id']),
        )
        changed += cur.rowcount
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description='按 account_name 回填账本引用悬空的流水（#2875）')
    parser.add_argument('--db', default=DEFAULT_DB, help='SQLite 数据库路径（默认 invest.db）')
    parser.add_argument('--apply', action='store_true', help='真正写库（缺省只读预览）')
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print('[错误] 数据库不存在: %s' % db_path)
        return 1

    uri = db_path.resolve().as_uri() + ('?mode=ro' if not args.apply else '')
    conn = sqlite3.connect(uri, uri=True)
    try:
        fixable, manual = plan_fixes(conn)
        print('库: %s（%s）' % (db_path, 'APPLY 写入' if args.apply else '只读预览'))
        print('\n可回填 %d 行：' % len(fixable))
        for r in fixable:
            print(
                '  tx#%-6d %s %s %s amount=%s account=%r → ledger %s'
                % (r['id'], r['created'], r['type'], r['symbol'] or '-', r['amount'], r['account_name'], r['ledger_id'])
            )
        if manual:
            print('\n需人工处理 %d 行（本次跳过）：' % len(manual))
            for r in manual:
                print(
                    '  tx#%-6d %s %s account=%r 原因：%s'
                    % (r['id'], r['created'], r['type'], r['account_name'], r['reason'])
                )

        if not args.apply:
            print('\n[预览] 未修改任何数据。加 --apply 执行回填。')
            return 0

        conn.execute('BEGIN')
        changed = apply_fixes(conn, fixable)
        conn.commit()
        remain = conn.execute(
            'SELECT COUNT(*) FROM transactions WHERE ' + _DANGLING_LEDGER + ' AND position_id IS NULL'
        ).fetchone()[0]
        print('\n[APPLY] 回填 %d 行；剩余账本悬空且无持仓的行 %d（应为需人工行数）。' % (changed, remain))
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())

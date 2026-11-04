# -*- coding: utf-8 -*-
"""合并「同一销售机构被拆成多个账户」的账本（默认 dry-run）。

## 为什么会有这个脚本

E账户导入的 `_get_or_create_channel_ledger` 曾把查重键写成
`(family_id, ledger_type='fund', sales_institution_id)`，并把新建账本的 `ledger_type`
硬编码成 `'fund'`。用户手工建的银行 / 券商账户是 `bank` / `stock` 类型，于是**永远查不到**，
每次导入都新建一本幽灵账户。本地库实测（2026-10-28）：

============================  ==============  =======  ======  ==========================
机构                          真账户           流水     持仓    幽灵账户
============================  ==============  =======  ======  ==========================
72 深圳前海微众银行(城市商业银行)  id=3 微众银行(bank)  416      1      id=18 深圳前海微众银行(fund)
203 银河证券(证券公司)           id=12 同花顺(bank→stock) 1211   27      id=14 中国银河证券(fund)
============================  ==============  =======  ======  ==========================

两对幽灵的 `created_at` 精确到同一次导入（2026-08-17 19:07:51），幽灵侧一律 0 流水。
代码已修（查重不看类型、`ledger_type` 由 `channel_category` 派生），但**已建出来的还在**。

## 判据

- **分组键 `(family_id, sales_institution_id)`**：同一机构只能有一个账户。刻意不带
  `ledger_type` —— 那正是原 bug 的分组方式；也不带 `channel_category`，因为用户可能
  已经把幽灵的渠道类别改成和真账户一样（本次事故里就是这么改的，两个都是 bank）。
- **keeper（留下的那本）= 流水最多 > 持仓最多 > id 最小**。流水是「这个账户真被用过」的
  铁证；幽灵恰好持仓多、流水 0，所以不能按持仓选。
- **同 symbol 重叠 → 整组跳过并报告**。`uq_positions_ledger_symbol` 让两本账持有同一只
  基金时物理上迁不过去，删哪一行是用户的数据决策。
- **资产快照按日相加**：`asset_snapshots` 是「某日某账户的资产」，合并后账户只有一个，
  当日资产就是两部分之和；同日无 keeper 行时直接改 `ledger_id`。`asset_snapshots` 的
  `idx_asset_snapshots_ledger_date` 不是唯一索引，但仍按 (date) 去重合并，避免同日两行。
- **盈亏快照要求成员全为零才删**：`pnl_daily_snapshots` 的重心（rate_bp / state /
  caliber_version）无法简单相加。实测幽灵侧 358 条全为 0/None（无流水即无盈亏），
  直接删；一旦发现非零就拒绝整组，交人工。
- **只在「迁完之后一个引用都不剩」时才删账户**。`discrepancies` / `recurring_plans` /
  `ledgers.linked_cash_ledger_id` 等白名单外表若有引用，整组拒绝。

## 安全设计

- **必须显式 `--db`**：标准库 `sqlite3` 直连，不导入应用会话（避免环境里配了远程库时误连）。
- **默认 dry-run**：只打印计划；写库需显式 `--apply`。
- **apply 先整库备份**：`--backup-db` 指定路径（默认 `<db>.bak-<时间戳>`）。
- **单事务 + 事后断言**：持仓/流水/资产行数守恒、被删账户零残留引用，任一失败整体回滚。

## 用法

.. code-block:: text

    cd backend
    python scripts/merge_institution_ledgers.py --db invest.db            # 预演
    python scripts/merge_institution_ledgers.py --db invest.db --apply    # 执行
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sqlite3
import sys

# 迁移时按顺序处理的引用表：先 FK 约束强的，再普通引用。
# 白名单之外、且含 ledger_id 列的表若有引用，整组拒绝（既不迁也不删）。
LEDGER_REF_TABLES = ('positions', 'transactions', 'assets', 'position_import_meta')

# 只迁业务数据、不迁历史快照的表（快照单独按日合并，语义不同）
SNAPSHOT_TABLES = ('asset_snapshots', 'pnl_daily_snapshots')

# 资产快照的数值列（按日相加）
ASSET_SNAPSHOT_SUM_COLS = (
    'total_assets',
    'total_liabilities',
    'net_worth',
    'realized_pnl_cents',
    'unrealized_pnl_cents',
    'total_pnl_cents',
    'money_fund_income_cents',
)


def q(con: sqlite3.Connection, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    return con.execute(sql, args).fetchall()


def one(con: sqlite3.Connection, sql: str, args: tuple = ()):
    row = con.execute(sql, args).fetchone()
    return row[0] if row else None


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in q(con, f'PRAGMA table_info({table})')}


def ledgers_with_institution(con: sqlite3.Connection) -> list[dict]:
    rows = q(
        con,
        """
        select l.id, l.name, l.ledger_type, l.channel_category, l.sales_institution_id,
               l.family_id, l.is_active, l.created_at,
               s.org_name, s.org_type
        from ledgers l
        join sales_institutions s on s.id = l.sales_institution_id
        where l.sales_institution_id is not null
        order by l.sales_institution_id, l.id
        """,
    )
    return [dict(r) for r in rows]


def ledger_stats(con: sqlite3.Connection, ledger_id: int) -> dict:
    return {
        'transactions': one(con, 'select count(*) from transactions where ledger_id=?', (ledger_id,)) or 0,
        'positions': one(con, 'select count(*) from positions where ledger_id=?', (ledger_id,)) or 0,
        'assets': one(con, 'select count(*) from assets where ledger_id=?', (ledger_id,)) or 0,
    }


def pick_keeper(con: sqlite3.Connection, ledgers: list[dict]) -> tuple[dict, list[dict]]:
    """keeper = 流水最多 > 持仓最多 > id 最小；其余为待合并的成员。"""
    stats = {led['id']: ledger_stats(con, led['id']) for led in ledgers}
    ordered = sorted(
        ledgers,
        key=lambda led: (
            -stats[led['id']]['transactions'],
            -stats[led['id']]['positions'],
            led['id'],
        ),
    )
    return ordered[0], ordered[1:]


def check_blockers(con: sqlite3.Connection, member: dict, keeper: dict) -> list[str]:
    """返回阻止合并的原因（空 = 可以合）。"""
    problems: list[str] = []
    mid, kid = member['id'], keeper['id']

    # 1. 同 symbol 持仓冲突（唯一约束会挡）
    overlap = q(
        con,
        """select a.symbol from positions a join positions b on b.symbol = a.symbol and b.ledger_id = ?
           where a.ledger_id = ?""",
        (kid, mid),
    )
    if overlap:
        problems.append(f'与 keeper 有 {len(overlap)} 只同标的重叠持仓: {[r[0] for r in overlap]}')

    # 2. 盈亏快照非零（无法简单相加）
    if 'pnl_daily_snapshots' in {r[0] for r in q(con, "select name from sqlite_master where type='table'")}:
        nonzero = one(
            con,
            """select count(*) from pnl_daily_snapshots
               where ledger_id=? and (coalesce(daily_pnl_cents,0) <> 0 or coalesce(net_worth_cents,0) <> 0)""",
            (mid,),
        )
        if nonzero:
            problems.append(f'盈亏快照有 {nonzero} 条非零数据，无法简单合并')

    # 3. 白名单之外的表有引用
    known = set(LEDGER_REF_TABLES) | set(SNAPSHOT_TABLES) | {'position_import_meta'}
    tables = [r[0] for r in q(con, "select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
    for table in tables:
        cols = table_columns(con, table)
        if table in known or 'ledger_id' not in cols:
            continue
        n = one(con, f'select count(*) from {table} where ledger_id=?', (mid,))
        if n:
            problems.append(f'{table} 有 {n} 行引用（白名单外表，需人工判断）')

    # 4. 被别的账本当作已绑定的现金账户
    n = one(con, 'select count(*) from ledgers where linked_cash_ledger_id=?', (mid,))
    if n:
        problems.append(f'被 {n} 个账本绑定为现金账户（linked_cash_ledger_id）')

    return problems


def build_plan(con: sqlite3.Connection) -> list[dict]:
    by_inst: dict[int, list[dict]] = {}
    for led in ledgers_with_institution(con):
        by_inst.setdefault(led['sales_institution_id'], []).append(led)

    plans: list[dict] = []
    for inst_id, ledgers in sorted(by_inst.items()):
        if len(ledgers) < 2:
            continue
        keeper, members = pick_keeper(con, ledgers)
        plans.append({'institution_id': inst_id, 'keeper': keeper, 'members': members, 'blockers': {}})
        for member in members:
            plans[-1]['blockers'][member['id']] = check_blockers(con, member, keeper)
    return plans


def print_plan(con: sqlite3.Connection, plans: list[dict]) -> None:
    if not plans:
        print('未发现同一销售机构下的重复账户。')
        return
    for plan in plans:
        keeper = plan['keeper']
        kstats = ledger_stats(con, keeper['id'])
        print(
            f'\n机构 {plan["institution_id"]} {keeper["org_name"]} [{keeper["org_type"]}]'
            f' → 保留 id={keeper["id"]}「{keeper["name"]}」'
            f' ({keeper["ledger_type"]}/{keeper["channel_category"]},'
            f' 流水 {kstats["transactions"]} / 持仓 {kstats["positions"]} / 资产 {kstats["assets"]})'
        )
        for member in plan['members']:
            mstats = ledger_stats(con, member['id'])
            flag = 'BLOCKED' if plan['blockers'][member['id']] else '可合并'
            print(
                f'  - id={member["id"]}「{member["name"]}」'
                f' ({member["ledger_type"]}/{member["channel_category"]},'
                f' 流水 {mstats["transactions"]} / 持仓 {mstats["positions"]} / 资产 {mstats["assets"]}) [{flag}]'
            )
            for problem in plan['blockers'][member['id']]:
                print(f'      ✗ {problem}')
            if not plan['blockers'][member['id']]:
                moved = {
                    'positions': one(con, 'select count(*) from positions where ledger_id=?', (member['id'],)),
                    'transactions': one(con, 'select count(*) from transactions where ledger_id=?', (member['id'],)),
                    'assets': one(con, 'select count(*) from assets where ledger_id=?', (member['id'],)),
                    'meta.ledger_id': one(
                        con, 'select count(*) from position_import_meta where ledger_id=?', (member['id'],)
                    ),
                    'meta.attributed_to': one(
                        con,
                        'select count(*) from position_import_meta where attributed_to_ledger_id=?',
                        (member['id'],),
                    ),
                    'asset_snapshots': one(
                        con, 'select count(*) from asset_snapshots where ledger_id=?', (member['id'],)
                    ),
                    'pnl_daily': one(
                        con, 'select count(*) from pnl_daily_snapshots where ledger_id=?', (member['id'],)
                    ),
                }
                print('      迁移: ' + ', '.join(f'{k}={v}' for k, v in moved.items() if v))


def merge_asset_snapshots(con: sqlite3.Connection, member_id: int, keeper_id: int) -> tuple[int, int]:
    """把成员的资产快照按日并入 keeper：有同日行则数值相加，否则改 ledger_id。

    Returns: (相加条数, 直接改指条数)
    """
    merged = moved = 0
    rows = q(con, 'select * from asset_snapshots where ledger_id=?', (member_id,))
    for row in rows:
        existing = con.execute(
            'select * from asset_snapshots where ledger_id=? and snapshot_date=?',
            (keeper_id, row['snapshot_date']),
        ).fetchone()
        if existing is None:
            con.execute(
                'update asset_snapshots set ledger_id=? where id=?',
                (keeper_id, row['id']),
            )
            moved += 1
            continue
        for col in ASSET_SNAPSHOT_SUM_COLS:
            a = existing[col]
            b = row[col]
            if a is None and b is None:
                continue
            con.execute(
                f'update asset_snapshots set {col}=? where id=?',
                ((a or 0) + (b or 0), existing['id']),
            )
        con.execute('delete from asset_snapshots where id=?', (row['id'],))
        merged += 1
    return merged, moved


def merge_ledger(con: sqlite3.Connection, member: dict, keeper: dict) -> dict:
    """把成员账本的全部引用迁到 keeper，然后删除成员。返回动作计数。"""
    mid, kid = member['id'], keeper['id']
    keeper_name = keeper['name']
    actions: dict[str, int] = {}

    # 1. 业务数据：改绑 + 刷新 account_name 冗余快照（账户改名规则 #1354）
    for table in ('positions', 'transactions', 'assets'):
        cols = table_columns(con, table)
        if 'account_name' in cols:
            cur = con.execute(
                f'update {table} set ledger_id=?, account_name=? where ledger_id=?',
                (kid, keeper_name, mid),
            )
        else:
            cur = con.execute(f'update {table} set ledger_id=? where ledger_id=?', (kid, mid))
        actions[table] = cur.rowcount

    # 2. 导入元数据：落点与归因目标都改指 keeper
    cur = con.execute('update position_import_meta set ledger_id=? where ledger_id=?', (kid, mid))
    actions['meta.ledger_id'] = cur.rowcount
    cur = con.execute(
        'update position_import_meta set attributed_to_ledger_id=? where attributed_to_ledger_id=?',
        (kid, mid),
    )
    actions['meta.attributed_to'] = cur.rowcount

    # 3. 资产快照：按日相加
    merged, moved = merge_asset_snapshots(con, mid, kid)
    actions['snapshots_merged'] = merged
    actions['snapshots_moved'] = moved

    # 4. 盈亏快照：成员必须全零（check_blockers 已保证），直接删
    cur = con.execute('delete from pnl_daily_snapshots where ledger_id=?', (mid,))
    actions['pnl_daily_deleted'] = cur.rowcount

    # 5. 删账户
    con.execute('delete from ledgers where id=?', (mid,))
    actions['ledger_deleted'] = 1
    return actions


def assert_consistent(con: sqlite3.Connection, before: dict, deleted_ids: list[int]) -> list[str]:
    errors: list[str] = []
    for table in ('positions', 'transactions', 'assets'):
        after = one(con, f'select count(*) from {table}') or 0
        if after != before[table]:
            errors.append(f'{table} 行数变化: {before[table]} → {after}')
    for ledger_id in deleted_ids:
        for table in LEDGER_REF_TABLES:
            n = one(con, f'select count(*) from {table} where ledger_id=?', (ledger_id,))
            if n:
                errors.append(f'{table}.ledger_id 仍残留 {n} 行指向已删账户 {ledger_id}')
        for table in SNAPSHOT_TABLES:
            n = one(con, f'select count(*) from {table} where ledger_id=?', (ledger_id,))
            if n:
                errors.append(f'{table} 仍残留 {n} 行指向已删账户 {ledger_id}')
        n = one(con, 'select count(*) from position_import_meta where attributed_to_ledger_id=?', (ledger_id,))
        if n:
            errors.append(f'position_import_meta.attributed_to_ledger_id 仍残留 {n} 行')
    return errors


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description='合并同一销售机构下的重复账本（默认 dry-run）')
    parser.add_argument('--db', required=True, help='SQLite 数据库路径（必填，防误连生产）')
    parser.add_argument('--apply', action='store_true', help='真正写库（默认只预演）')
    parser.add_argument('--backup-db', default=None, help='apply 前的整库备份路径')
    args = parser.parse_args(argv)

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')

    plans = build_plan(con)
    print_plan(con, plans)
    if not plans:
        return 0

    runnable = [p for p in plans if not any(p['blockers'].values())]
    blocked = len(plans) - len(runnable)
    print(f'\n可执行 {len(runnable)} 组，{blocked} 组因冲突跳过。')

    if not args.apply:
        print('\n（dry-run，未写库。加 --apply 执行，执行前会自动备份整库。）')
        return 0
    if not runnable:
        print('没有可执行的合并，退出。')
        return 1

    backup = args.backup_db or f'{args.db}.bak-{dt.datetime.now().strftime("%Y%m%d-%H%M%S")}'
    shutil.copy2(args.db, backup)
    print(f'\n已备份整库 → {backup}')

    before = {t: one(con, f'select count(*) from {t}') or 0 for t in ('positions', 'transactions', 'assets')}
    deleted: list[int] = []
    try:
        con.execute('BEGIN IMMEDIATE')
        for plan in runnable:
            keeper = plan['keeper']
            for member in plan['members']:
                # 事务内再查一次，防止预演与执行之间数据变动
                problems = check_blockers(con, member, keeper)
                if problems:
                    raise RuntimeError(f'执行前复查失败（{member["id"]}）：{problems}')
                actions = merge_ledger(con, member, keeper)
                deleted.append(member['id'])
                print(
                    f'  合并 id={member["id"]}「{member["name"]}」→ id={keeper["id"]}「{keeper["name"]}」: '
                    + ', '.join(f'{k}={v}' for k, v in actions.items() if v)
                )
        errors = assert_consistent(con, before, deleted)
        if errors:
            raise RuntimeError('; '.join(errors))
        con.commit()
    except Exception as exc:  # noqa: BLE001 - 任何失败都整体回滚
        con.rollback()
        print(f'\n失败并已回滚: {exc}', file=sys.stderr)
        print(f'整库备份仍在: {backup}', file=sys.stderr)
        return 1

    print(f'\n完成：删除 {len(deleted)} 个重复账户（{deleted}），行数守恒断言通过。')
    print(f'备份: {backup}')
    con.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

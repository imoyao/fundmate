# -*- coding: utf-8 -*-
"""合并「同一销售渠道被拆成多个账户」的重复渠道账本（默认 dry-run）。

## 为什么会有这个脚本

2026-10-28 用户实测 E账户导入：一次导入之后库里凭空多出十几组同名渠道账户
（``珠海盈米基金销售`` ×2、``富国基金`` ×3、``招商银行`` ×3 …）。

根因在 ``orchestrator_holdings._get_or_create_channel_ledger``：查/建键里含
``external_account_code``，而导入侧传进去的是**交易账号**（同一渠道下每张绑定卡 /
每个基金账号各不同）。于是「多一个交易账号」就等于「多一个账户」。

代码已修（一个渠道一个账户、交易账号退回持仓级），但**已经建出来的重复账户还在**。
本脚本负责把存量数据收敛回去：**先选一个账户留下来，把引用迁过去，清空的才删**。

## 判据（宁可留多，不可删错）

- **分组键** ``(family_id, ledger_type='fund', 关联销售机构)``；未关联机构的按 ``name`` 分组。
  先尝试给未关联机构的渠道账户补关联（走 ``institution_resolver`` 同一份判据）——
  否则「且慢」与「珠海盈米基金销售」会永远算两个渠道。
- **keeper（留下来的那条）= 持仓最多，其次 id 最小**。空壳账户往往 id 更小，
  按 id 选会让用户看到「账户里没钱」。
- **同标的重叠是本 bug 的产物，必须显式选口径**（``--on-duplicate``）：
  ``positions`` 上有唯一约束 ``uq_positions_ledger_symbol (ledger_id, symbol)``，
  两个账户持有同一只基金时**物理上迁不过去**。三种处置：

  ==================  ==========================================================
  ``skip``（默认）    有重叠的整组不动，只报告。**默认值刻意保守**：删哪一行是
                      用户的数据决策，不是脚本能替的。
  ``keep-keeper``     删成员账户里的重叠行（保留现有账户的旧行），其余行照常迁入。
  ``keep-newest``     删现有账户里的重叠行，把成员账户的行迁进来（导入快照较新时用）。
  ==================  ==========================================================

  被删的持仓行**必须没有任何** ``transactions`` / ``position_strategy_tags`` 引用，
  否则该组拒绝执行（删持仓会让流水失去落点）。
- **只在「迁完之后一个引用都不剩」时才删账户**。历史快照类表
  （``asset_snapshots`` / ``pnl_daily_snapshots``）**不迁**：它们是「某日某账户的资产状态」，
  合过去会篡改历史口径，因此它们把删除卡住——账户留下，人工判断。
  白名单之外的表同理（既不迁也不删）。

## 安全设计

- **必须显式 ``--db``**：用标准库 ``sqlite3`` 直连指定文件，**不导入应用会话**
  ——避免环境里配了 ``SUPABASE_DATABASE_URL`` 时误连生产库。
- **默认 dry-run**：只打印计划；写库需显式 ``--apply``。
- **apply 先备份**：把将被删除的 ``ledgers`` 行与被改动的引用导出成可回放的 ``.sql``
  （``--backup-out`` 可改路径），出问题直接 ``sqlite3 invest.db < backup.sql`` 回灌。
- **单事务 + 事后断言**：迁移后行数守恒、被删账户零残留引用；任一失败整体回滚并非零退出。

## 用法

.. code-block:: text

    cd backend
    python scripts/dedupe_channel_ledgers.py --db invest.db                        # dry-run（默认不碰重叠持仓）
    python scripts/dedupe_channel_ledgers.py --db invest.db --on-duplicate keep-newest   # 看新口径的计划
    python scripts/dedupe_channel_ledgers.py --db invest.db --on-duplicate keep-newest --apply
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

#: 允许把引用迁到 keeper 的（表, 列）。白名单之外的 ledger 引用一律视为「挡删除」——
#: 迁错外键几乎无从发现，留一个空壳账户却一眼可见。
MIGRATE_REFS = (
    ('positions', 'ledger_id'),
    ('position_import_meta', 'ledger_id'),
    ('position_import_meta', 'attributed_to_ledger_id'),
    ('assets', 'ledger_id'),
    ('transactions', 'ledger_id'),
    ('discrepancies', 'ledger_id'),
    ('recurring_plans', 'ledger_id'),
)

#: 明确「不迁、且挡删除」的表（历史快照 / 互链），附原因写进计划里给人看。
BLOCKING_REFS = (
    ('asset_snapshots', 'ledger_id', '历史资产快照按「账户+日期」记录，合并会篡改历史口径'),
    ('pnl_daily_snapshots', 'ledger_id', '历史盈亏快照，同上'),
    ('ledgers', 'linked_cash_ledger_id', '现金账户互链，指向关系需人工判断'),
)


# --------------------------------------------------------------------------- #
# 只读查询
# --------------------------------------------------------------------------- #
def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in con.execute(f'pragma table_info("{table}")')}
    except sqlite3.Error:
        return set()


def count_ref(con: sqlite3.Connection, table: str, column: str, ledger_id: int) -> int:
    if column not in table_columns(con, table):
        return 0
    return con.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" = ?', (ledger_id,)).fetchone()[0]


def unknown_ref_tables(con: sqlite3.Connection) -> list[tuple[str, str]]:
    """白名单之外、但带 ledger 引用的（表, 列）—— 一律挡删除。"""
    known = {t for t, _c in MIGRATE_REFS} | {t for t, _c, _w in BLOCKING_REFS}
    found = []
    tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for table in tables:
        if table in known or table.startswith('sqlite_'):
            continue
        cols = table_columns(con, table)
        for column in ('ledger_id', 'attributed_to_ledger_id'):
            if column in cols:
                found.append((table, column))
    return found


class InstitutionLookup:
    """把渠道名解析到 AMAC 销售机构——**复用产品代码**，不在这里重写一份判据。

    两处各写一份匹配规则正是本次事故的成因之一；脚本若自己再写第三份，
    下次用户看到的就是「脚本说能合、代码说不是一家」。
    """

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._cache: dict[str, tuple[int | None, str | None]] = {}
        self._session = None
        self._engine = None

    def _resolver(self):
        if self._session is not None:
            return self._session
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.services.institution_resolver import SalesInstitutionResolver

        uri = f'sqlite:///file:{self._db_path.as_posix()}?mode=ro&uri=true'
        self._engine = create_engine(uri)
        self._session = SalesInstitutionResolver(sessionmaker(bind=self._engine)())
        return self._session

    def __call__(self, name: str) -> tuple[int | None, str | None]:
        if name in self._cache:
            return self._cache[name]
        inst = self._resolver().resolve(name)
        result = (inst.id, inst.org_type) if inst else (None, None)
        self._cache[name] = result
        return result

    def close(self):
        if self._session is not None:
            self._session.db.close()
        if self._engine is not None:
            self._engine.dispose()


# --------------------------------------------------------------------------- #
# 计划
# --------------------------------------------------------------------------- #
class Group:
    """一组应被收敛成一个的渠道账户。"""

    def __init__(self, key, keeper: dict, members: list[dict]):
        self.key = key
        self.keeper = keeper
        self.members = members
        self.refuse_reason: str | None = None
        self.blocked: dict[int, list[tuple[str, str, int, str]]] = {}
        self.migrate: dict[int, list[tuple[str, str, int]]] = {}
        self.deletable: list[int] = []
        #: 重叠持仓：{(member_id, symbol): (member_position_id, keeper_position_id)}
        self.overlaps: dict[tuple[int, str], tuple[int, int]] = {}
        #: 重叠行是否被流水/标签引用（被引用则拒绝删行）
        self.overlap_refs: list[tuple[int, str, int]] = []
        #: ledger_id -> 可清理的陈旧快照行 id（快照日期早于该账户创建日）
        self.stale_snaps: dict[int, list[int]] = {}

    @property
    def keeper_id(self) -> int:
        return self.keeper['id']


def fetch_fund_ledgers(con: sqlite3.Connection) -> list[dict]:
    cols = table_columns(con, 'ledgers')
    if not cols:
        raise SystemExit('❌ ledgers 表不存在，--db 指错了？')
    select = [
        'id',
        'name',
        'ledger_type',
        'family_id',
        'sales_institution_id',
        'channel_category',
        'created_at',
    ]
    rows = con.execute(f'SELECT {", ".join(select)} FROM ledgers ORDER BY id').fetchall()
    return [dict(zip(select, row)) for row in rows]


def ledger_position_counts(con: sqlite3.Connection) -> dict[int, int]:
    return {
        row[0]: row[1]
        for row in con.execute('SELECT ledger_id, COUNT(*) FROM positions GROUP BY ledger_id')
        if row[0] is not None
    }


def ledger_snapshot_counts(con: sqlite3.Connection) -> dict[int, int]:
    """每个账户的资产快照条数——“历史厚度”，用于选 keeper（见 build_plan 注释）。"""
    if not table_columns(con, 'asset_snapshots'):
        return {}
    return {
        row[0]: row[1]
        for row in con.execute('SELECT ledger_id, COUNT(*) FROM asset_snapshots GROUP BY ledger_id')
        if row[0] is not None
    }


def stale_snapshot_ids(con: sqlite3.Connection, ledger: dict) -> list[int]:
    """该账户名下「日期严格早于账户创建日」的资产快照行 id。

    账户不可能在创建之前拥有快照，因此这些行只可能来自 id 被复用的前任（已删账户）。
    创建日当天及之后的快照一律视为真历史，不返回（保守口径）。
    """
    created = (ledger.get('created_at') or '')[:10]
    if not created or not table_columns(con, 'asset_snapshots'):
        return []
    return [
        row[0]
        for row in con.execute(
            'SELECT id FROM asset_snapshots WHERE ledger_id = ? AND snapshot_date < ?',
            (ledger['id'], created),
        )
    ]


def build_plan(
    con: sqlite3.Connection,
    lookup: InstitutionLookup,
    on_duplicate: str,
    purge_stale_snapshots: bool = False,
) -> tuple[list[Group], dict[int, tuple[int, str]]]:
    from app.domains.ledgers.constants import map_org_type_to_channel_category

    fund_ledgers = [led for led in fetch_fund_ledgers(con) if led['ledger_type'] == 'fund']

    # 阶段 1：未关联机构的渠道账户 → 尝试补关联（内存投影，写库在 apply）
    backfill: dict[int, tuple[int, str]] = {}
    for led in fund_ledgers:
        if led['sales_institution_id']:
            continue
        inst_id, org_type = lookup(led['name'])
        if inst_id is not None:
            backfill[led['id']] = (inst_id, map_org_type_to_channel_category(org_type))

    # 阶段 2：分组（用补关联后的机构 id；未命中才退化为 name）
    buckets: dict[tuple, list[dict]] = {}
    for led in fund_ledgers:
        inst_id = led['sales_institution_id'] or (backfill[led['id']][0] if led['id'] in backfill else None)
        key = (led['family_id'], inst_id if inst_id else ('name', led['name']))
        buckets.setdefault(key, []).append(led)

    pos_counts = ledger_position_counts(con)
    snap_counts = ledger_snapshot_counts(con)
    unknown_refs = unknown_ref_tables(con)

    groups: list[Group] = []
    for key, members in buckets.items():
        if len(members) < 2:
            continue
        # keeper = 历史最厚的账户：资产快照多 → 持仓多 → id 小。
        # 目标是「让有历史的账户活下来」，而不是机械地挑「最像旧的」或「持仓最多的」：
        #   - 只看持仓数：易方达 19（1 只 / 37 条历史快照）会输给今天新建的 29（2 只 /
        #     0 快照），历史账户的持仓被搬空、只剩一个有快照无持仓的壳；
        #   - 只看 created_at：支付宝 2（2026-05 建的空壳，0 持仓 0 快照）会赢过 13
        #     （20 只 / 37 条快照），同样是搬空有历史的那个。
        # 快照顺序之所以排第一：带快照的账户本就删不掉（BLOCKING_REFS），让它当 keeper
        # 才不会留下「快照还在、持仓没了」的空壳。
        ordered = sorted(
            members,
            key=lambda m: (
                -snap_counts.get(m['id'], 0),
                -pos_counts.get(m['id'], 0),
                m['id'],
            ),
        )
        group = Group(key=key, keeper=ordered[0], members=ordered[1:])

        # 同标的碰撞（uq_positions_ledger_symbol）-> 按 --on-duplicate 口径处置
        keeper_positions = {
            row[1]: row[0]
            for row in con.execute('SELECT id, symbol FROM positions WHERE ledger_id = ?', (group.keeper_id,))
        }
        for led in group.members:
            for pid, symbol in con.execute('SELECT id, symbol FROM positions WHERE ledger_id = ?', (led['id'],)):
                if symbol not in keeper_positions:
                    continue
                keeper_pid = keeper_positions[symbol]
                group.overlaps[(led['id'], symbol)] = (pid, keeper_pid)
                # 只检查「本次要删掉的那一侧」：删哪边由口径决定，另一边被流水引用并不
                # 影响本次删除（那一行根本不删）。早先的实现把两侧引用数相加，于是
                # keeper 侧有流水就把整组判死——而 keep-keeper 删的恰恰不是 keeper 侧。
                if on_duplicate == 'keep-keeper':
                    doomed_pid = pid
                elif on_duplicate == 'keep-newest':
                    doomed_pid = keeper_pid
                else:
                    doomed_pid = None
                if doomed_pid is None:
                    continue
                for table in ('transactions', 'position_strategy_tags'):
                    if 'position_id' not in table_columns(con, table):
                        continue
                    cnt = con.execute(
                        f'SELECT COUNT(*) FROM "{table}" WHERE position_id = ?', (doomed_pid,)
                    ).fetchone()[0]
                    if cnt:
                        group.overlap_refs.append((led['id'], symbol, cnt))
        if group.overlap_refs:
            group.refuse_reason = '要删除的重复持仓被流水/标签引用，删行会让流水失去落点: ' + '; '.join(
                f'ledger {lid} {sym} 引用 {cnt} 行' for lid, sym, cnt in group.overlap_refs
            )
        elif group.overlaps and on_duplicate == 'skip':
            group.refuse_reason = (
                f'两账户持有相同标的 {len(group.overlaps)} 只（撞 uq_positions_ledger_symbol）；'
                '用 --on-duplicate keep-keeper|keep-newest 指定保留哪一侧'
            )

        for led in group.members:
            refs = []
            for table, column in MIGRATE_REFS:
                cnt = count_ref(con, table, column, led['id'])
                if cnt:
                    refs.append((table, column, cnt))
            group.migrate[led['id']] = refs

            blocks = []
            for table, column, why in BLOCKING_REFS:
                cnt = count_ref(con, table, column, led['id'])
                if not cnt:
                    continue
                if table == 'asset_snapshots' and purge_stale_snapshots:
                    stale_ids = stale_snapshot_ids(con, led)
                    if stale_ids and len(stale_ids) == cnt:
                        # 全部陈旧 ⇒ 没有一条可能描述本账户，可连账户一起回收
                        group.stale_snaps[led['id']] = stale_ids
                        continue
                blocks.append((table, column, cnt, why))
            for table, column in unknown_refs:
                cnt = count_ref(con, table, column, led['id'])
                if cnt:
                    blocks.append((table, column, cnt, '白名单外引用，语义未确认'))
            if blocks:
                group.blocked[led['id']] = blocks
            elif not group.refuse_reason:
                group.deletable.append(led['id'])
        groups.append(group)
    return groups, backfill


# --------------------------------------------------------------------------- #
# 打印
# --------------------------------------------------------------------------- #
def print_plan(con: sqlite3.Connection, groups: list[Group], backfill: dict[int, tuple[int, str]]) -> None:
    pos_counts = ledger_position_counts(con)
    total_before = con.execute('SELECT COUNT(*) FROM positions').fetchone()[0]
    print(f'\n持仓总数（迁移前）：{total_before}；重复渠道账户组：{len(groups)}')
    mergeable = [g for g in groups if not g.refuse_reason and g.deletable]
    to_delete = [lid for g in groups for lid in g.deletable]
    for idx, group in enumerate(groups, 1):
        keeper = group.keeper
        print('─' * 78)
        print(f'[{idx}] 分组 {group.key}')
        print(
            f'    keeper: id={keeper["id"]} name={keeper["name"]!r} '
            f'inst={keeper["sales_institution_id"]} 持仓={pos_counts.get(keeper["id"], 0)}'
        )
        for led in group.members:
            print(
                f'    合并 -> id={led["id"]} name={led["name"]!r} '
                f'inst={led["sales_institution_id"]} 持仓={pos_counts.get(led["id"], 0)}'
            )
            print(f'         可迁引用：{group.migrate.get(led["id"]) or "无"}')
            overlap = sorted(sym for (lid, sym) in group.overlaps if lid == led['id'])
            if overlap:
                shown = overlap[:8] + (['…'] if len(overlap) > 8 else [])
                print(f'         重叠标的 {len(overlap)} 只（同渠道同基金两行）：{shown}')
            for table, column, cnt, why in group.blocked.get(led['id'], []):
                print(f'         ⛔ 挡删除：{table}.{column}={cnt}（{why}）')
            if group.refuse_reason:
                print(f'         ⛔ 整组拒绝：{group.refuse_reason}')
    print('─' * 78)
    print(f'\n可执行合并组：{len(mergeable)} / 共 {len(groups)} 组')
    print(f'将删除的空账户：{to_delete or "无"}')
    if backfill:
        print(
            f'将补关联机构的渠道账户：{len(backfill)} 个 -> '
            + ', '.join(f'{lid}->{inst}' for lid, (inst, _cat) in sorted(backfill.items()))
        )
    stale_total = sum(len(v) for g in groups if not g.refuse_reason for v in g.stale_snaps.values())
    if stale_total:
        per = {lid: len(v) for g in groups for lid, v in g.stale_snaps.items()}
        print(f'将清理的陈旧资产快照：{stale_total} 行（日期早于账户创建日，属 id 复用留下的孤儿）{per}')
    kept_blocked = [
        led['id'] for g in groups if not g.refuse_reason for led in g.members if led['id'] not in g.deletable
    ]
    if kept_blocked:
        print(f'账户本身保留、持仓已按口径处置（有不可迁移的历史引用，如资产快照）：{kept_blocked}')
    blocked = len(groups) - len(mergeable)
    if blocked:
        print(f'需人工处理：{blocked} 组（原因见上面的 ⛔ 行）')


# --------------------------------------------------------------------------- #
# 执行
# --------------------------------------------------------------------------- #
def sql_literal(value) -> str:
    if value is None:
        return 'NULL'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, bytes):
        return "X'" + value.hex() + "'"
    return "'" + str(value).replace("'", "''") + "'"


def dump_rows(con: sqlite3.Connection, table: str, ids: list[int]) -> str:
    if not ids:
        return ''
    cols = [row[1] for row in con.execute(f'pragma table_info("{table}")')]
    marks = ','.join('?' * len(ids))
    rows = con.execute(f'SELECT {", ".join(cols)} FROM "{table}" WHERE id IN ({marks})', ids).fetchall()
    lines = [f'-- 回灌 {table}（{len(rows)} 行，apply 前的原样）']
    for row in rows:
        values = ', '.join(sql_literal(v) for v in row)
        lines.append(f'INSERT OR REPLACE INTO "{table}" ({", ".join(cols)}) VALUES ({values});')
    return '\n'.join(lines) + '\n'


def delete_positions(con: sqlite3.Connection, position_ids: list[int], backup_parts: list[str]) -> int:
    """删除持仓行，并把「持仓行 + 其 import_meta」都写进备份（meta 有 position_id 唯一约束）。"""
    if not position_ids:
        return 0
    backup_parts.append(dump_rows(con, 'positions', position_ids))
    marks = ','.join('?' * len(position_ids))
    meta_ids = [
        row[0]
        for row in con.execute(f'SELECT id FROM position_import_meta WHERE position_id IN ({marks})', position_ids)
    ]
    backup_parts.append(dump_rows(con, 'position_import_meta', meta_ids))
    con.execute(f'DELETE FROM position_import_meta WHERE position_id IN ({marks})', position_ids)
    con.execute(f'DELETE FROM positions WHERE id IN ({marks})', position_ids)
    return len(position_ids)


def apply_plan(
    con: sqlite3.Connection,
    groups: list[Group],
    backfill: dict[int, tuple[int, str]],
    backup_out: Path,
    on_duplicate: str,
) -> int:
    positions_before = con.execute('SELECT COUNT(*) FROM positions').fetchone()[0]
    backup_parts = ['-- dedupe_channel_ledgers 回灌脚本\nPRAGMA foreign_keys=OFF;\nBEGIN;\n']
    moved = 0

    try:
        # 1) 补关联（未关联机构的渠道账户 -> 机构 + 渠道分类）
        #    与「能不能合并」无关：它只写两个字段、无副作用，被拒绝合并的组同样该补。
        for led_id, (inst_id, category) in sorted(backfill.items()):
            backup_parts.append(dump_rows(con, 'ledgers', [led_id]))
            con.execute(
                'UPDATE ledgers SET sales_institution_id = ?, '
                'channel_category = COALESCE(channel_category, ?) WHERE id = ?',
                (inst_id, category, led_id),
            )

        # 2) 处置重叠持仓（同渠道同基金两行）—— 必须在迁引用之前，否则撞唯一约束
        deleted_positions = 0
        if on_duplicate == 'keep-keeper':
            for group in groups:
                if group.refuse_reason:
                    continue
                doomed = [member_pid for (member_pid, _keeper_pid) in group.overlaps.values()]
                deleted_positions += delete_positions(con, doomed, backup_parts)
        elif on_duplicate == 'keep-newest':
            for group in groups:
                if group.refuse_reason:
                    continue
                doomed = [keeper_pid for (_member_pid, keeper_pid) in group.overlaps.values()]
                deleted_positions += delete_positions(con, doomed, backup_parts)

        # 3) 迁引用
        for group in groups:
            if group.refuse_reason:
                continue
            for led_id in [m['id'] for m in group.members if m['id'] in group.deletable]:
                for table, column, _cnt in group.migrate.get(led_id, []):
                    affected = [
                        row[0] for row in con.execute(f'SELECT id FROM "{table}" WHERE "{column}" = ?', (led_id,))
                    ]
                    backup_parts.append(dump_rows(con, table, affected))
                    con.execute(
                        f'UPDATE "{table}" SET "{column}" = ? WHERE "{column}" = ?',
                        (group.keeper_id, led_id),
                    )
                    moved += len(affected)

        # 4) 删账户（迁完零引用的才删）
        #    4a 先清陈旧快照：它们日期早于账户创建日，属 id 复用留下的孤儿行，
        #       不清就删不掉账户（BLOCKING_REFS）。全部陈旧才进 stale_snaps，见 build_plan。
        purged_snaps = 0
        for group in groups:
            if group.refuse_reason:
                continue
            for led_id in group.deletable:
                snap_ids = group.stale_snaps.get(led_id) or []
                if not snap_ids:
                    continue
                backup_parts.append(dump_rows(con, 'asset_snapshots', snap_ids))
                con.execute(
                    f'DELETE FROM asset_snapshots WHERE id IN ({",".join("?" * len(snap_ids))})',
                    snap_ids,
                )
                purged_snaps += len(snap_ids)

        deleted = []
        for group in groups:
            for led_id in group.deletable:
                backup_parts.append(dump_rows(con, 'ledgers', [led_id]))
                con.execute('DELETE FROM ledgers WHERE id = ?', (led_id,))
                deleted.append(led_id)

        # 5) 断言（结构判据，不做「预知删了多少行」的算术推断）
        problems = []
        positions_after = con.execute('SELECT COUNT(*) FROM positions').fetchone()[0]
        expected_positions = positions_before - deleted_positions
        if positions_after != expected_positions:
            problems.append(
                f'持仓行数 {positions_after} != 预期 {expected_positions}'
                f'（合并前 {positions_before}，按口径删除重叠行 {deleted_positions}）'
            )
        # ② 迁移表里不得再有行指向已删除账户（孤儿引用）
        for led_id in deleted:
            for table, column in MIGRATE_REFS:
                if count_ref(con, table, column, led_id):
                    problems.append(f'孤儿引用：{table}.{column} 仍指向已删除的 ledger {led_id}')
            for table, column, _why in BLOCKING_REFS:
                if count_ref(con, table, column, led_id):
                    problems.append(f'孤儿引用（历史表）：{table}.{column} 仍指向 ledger {led_id}')
        # ③ 计划内可删的账户必须消失；被挡住的账户必须原样还在（不许「顺手」删掉）
        for group in groups:
            for led_id in group.deletable:
                if led_id not in deleted:
                    problems.append(f'计划内应删的 ledger {led_id} 仍在库中')
            for led in group.members:
                if led['id'] in group.deletable:
                    continue
                exists = con.execute('SELECT COUNT(*) FROM ledgers WHERE id = ?', (led['id'],)).fetchone()[0]
                if not exists:
                    problems.append(f'被挡住的 ledger {led["id"]} 被误删（不应动它）')
            exists = con.execute('SELECT COUNT(*) FROM ledgers WHERE id = ?', (group.keeper_id,)).fetchone()[0]
            if not exists:
                problems.append(f'keeper {group.keeper_id} 被误删')

        if problems:
            con.rollback()
            print('\n❌ 断言失败，已回滚：')
            for p in problems:
                print('  -', p)
            return 1
    except Exception as exc:  # noqa: BLE001 - 任何一步失败都必须整体回滚
        con.rollback()
        print(f'\n❌ 执行失败，已回滚：{exc}')
        return 1

    backup_parts.append(f'\n-- 本次删除的账户: {deleted}\nCOMMIT;\n')
    backup_out.write_text(''.join(backup_parts), encoding='utf-8')
    con.commit()

    remaining = con.execute(
        "SELECT COUNT(*) FROM ledgers WHERE ledger_type = 'fund' AND sales_institution_id IS NULL"
    ).fetchone()[0]
    print(f'\n✅ 已提交：迁移引用 {moved} 行，删除重叠持仓 {deleted_positions} 行，删除账户 {deleted}')
    if purged_snaps:
        print(f'   清理陈旧资产快照 {purged_snaps} 行（日期早于账户创建日，已写入回灌脚本）')
    print(f'   备份（回灌）：{backup_out}')
    print(f'   仍未关联机构的渠道账户：{remaining} 个（名录外的基金公司直销属正常）')
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description='合并同一销售渠道的重复渠道账本（默认 dry-run）')
    parser.add_argument('--db', required=True, help='invest.db 路径（必填，避免误连生产库）')
    parser.add_argument('--apply', action='store_true', help='真正写库（默认仅打印计划）')
    parser.add_argument('--backup-out', default=None, help='回灌 SQL 输出路径（默认库旁 data/）')
    parser.add_argument(
        '--purge-stale-snapshots',
        action='store_true',
        help='一并清理「快照日期早于账户创建日」的陈旧 per-ledger 资产快照，使空壳账户可回收'
        '（只动全陈旧者；家庭级总资产快照不动）',
    )
    parser.add_argument(
        '--on-duplicate',
        choices=('skip', 'keep-keeper', 'keep-newest'),
        default='skip',
        help='同渠道同基金两行时怎么办：skip=不碰（默认）/ keep-keeper=删成员侧 / keep-newest=删现有侧',
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(f'❌ 库不存在：{db_path}')
        return 2
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    con = sqlite3.connect(str(db_path))
    lookup = InstitutionLookup(db_path)
    try:
        groups, backfill = build_plan(con, lookup, args.on_duplicate, args.purge_stale_snapshots)
        if not groups:
            print('✅ 没有发现重复的 fund 渠道账户，无需处理')
            return 0
        print_plan(con, groups, backfill)
        if not args.apply:
            print('\n（dry-run：未写库。确认无误后加 --apply）')
            return 0
        backup_out = (
            Path(args.backup_out).resolve()
            if args.backup_out
            else db_path.parent / 'data' / f'backup_dedupe_ledgers_{time.strftime("%Y%m%d_%H%M%S")}.sql'
        )
        backup_out.parent.mkdir(parents=True, exist_ok=True)
        return apply_plan(con, groups, backfill, backup_out, args.on_duplicate)
    finally:
        lookup.close()
        con.close()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

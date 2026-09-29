#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""#1662 审计 / 修复：symbol 形态是否符合其**交易场所（venue）**约定。

## 判据（唯一权威见 `app/core/venues.py`）

    EXCHANGE → {MARKET}{CODE6}（SH600519 / SZ159915）
    OTC      → **裸 6 位码**（004369）—— 绝不带交易所前缀
    无场所    → 原样（经理 MGR_* / 投顾组合 ZH* 等）

## venue 从哪来（逐表口径，与写入侧保持一致）

| 表           | venue 来源                                                   |
|--------------|--------------------------------------------------------------|
| positions    | `type`（ORM asset_type）→ `venue_of_asset_type`               |
| transactions | `asset_type`；为空时回退到 `position_id` 指向持仓的 `type`     |
| watchlist    | **已有 `venue` 列**（写入侧早已携带），为空才回退 asset_type     |

venue 解析**不再在本脚本内重复实现**：统一走 `app/core/venues.py::venue_of_row`
（显式声明 > 场内货基特例 > asset_type 缺省推断），与写入侧 / 迁移同一口径。

**场内货基例外**：`SH` 前缀 + 代码段 `^97\\d{4}$`（如 `SH970164` 银河水星现金添利）
资产类型是货基却属交易所，故显式判为 EXCHANGE、**不剥前缀**。与
`app/services/fund_utils._CODE_FALLBACK_RE` 那条「沪市现金管理 97xxxx」同源。

## 用法

    python scripts/audit_symbol_venue_conformance.py                 # 只读审计（默认库）
    python scripts/audit_symbol_venue_conformance.py --db <path>
    python scripts/audit_symbol_venue_conformance.py --apply         # 备份后修复
    python scripts/audit_symbol_venue_conformance.py --apply --merge # 连重复行一起合并
    python scripts/audit_symbol_venue_conformance.py --json

任何不合规行都会让退出码 = 1（可当 CI 门禁用）。

## 安全约束

- `--apply` 前**强制**用 SQLite backup API 备份（invest.db 有未 checkpoint 的 -wal，
  直接拷文件会漏掉最新事务）；
- 「同一标的并存两种写法」只有在**同一业务作用域内**才算缺陷：
  positions 的 `UNIQUE(ledger_id, symbol)` → 作用域 = (family_id, ledger_id)；
  watchlist 的 `UNIQUE(family_id, symbol, market, venue)` → 作用域 = (family_id, market)。
  **跨账户持仓同码是正常的**（同一只基金在多个账户各持一份），绝不能合并——
  这条是本脚本最容易犯的错，合并前会对作用域再断言一次；
- transactions **永不合并**（同一 symbol 多笔流水是正常业务），只做前缀归一；
- 合并按**份额加权**重算成交均价（整数域运算，避免 float 污染金融口径），
  并把所有引用表改指到保留行后再删除被并行。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sqlite3
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'backend'))

from app.core.symbol_utils import normalize_by_venue, strip_exchange_prefix, symbol_identity  # noqa: E402
from app.core.venues import EXCHANGE, OTC, venue_of_row  # noqa: E402

DEFAULT_DB = REPO_ROOT / 'backend' / 'invest.db'

# 逐表配置：symbol / asset_type / venue 列名 + 判定重复的业务作用域 + 引用列名
TABLES = {
    'positions': dict(
        pk='id',
        symbol='symbol',
        asset_type='type',
        venue=None,
        scope=('family_id', 'ledger_id'),
        ref_col='position_id',
        merge=True,
    ),
    'transactions': dict(
        pk='id',
        symbol='symbol',
        asset_type='asset_type',
        venue=None,
        scope=None,
        ref_col=None,
        merge=False,  # 同一 symbol 多笔流水正常，永不合并
    ),
    'watchlist': dict(
        pk='id',
        symbol='symbol',
        asset_type='asset_type',
        venue='venue',
        scope=('family_id', 'market'),
        ref_col='item_id',
        merge=True,
    ),
}


def expected_symbol(symbol: str, venue: str) -> str:
    """该行 symbol 的规范形态；venue 判不出（''）时原样返回。"""
    if not symbol:
        return symbol
    if venue == OTC:
        return strip_exchange_prefix(symbol)
    if venue == EXCHANGE:
        normalized, _market, _atype = normalize_by_venue(symbol, EXCHANGE)
        return normalized
    return symbol


def columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]


def all_tables(con: sqlite3.Connection) -> list[str]:
    return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]


def ref_tables(con: sqlite3.Connection, table: str) -> list[str]:
    """所有引用该表主键的表（合并时要改指）。"""
    col = TABLES[table]['ref_col']
    return [t for t in all_tables(con) if t != table and col in columns(con, t)]


def backup(db_path: pathlib.Path) -> pathlib.Path:
    """SQLite backup API 备份（含未 checkpoint 的 WAL 事务）。"""
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    dest = db_path.with_name(f'{db_path.name}.backup-venue-{stamp}')
    src = sqlite3.connect(f'file:{db_path.as_posix()}?mode=rw', uri=True)
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return dest


def audit(con: sqlite3.Connection) -> list[dict]:
    """逐表找出形态不合规的行。"""
    findings: list[dict] = []
    pos_type = {r[0]: r[1] for r in con.execute('SELECT id, type FROM positions').fetchall()}

    for table, cfg in TABLES.items():
        cols = [cfg['pk'], cfg['symbol'], cfg['asset_type']]
        if cfg['venue']:
            cols.append(cfg['venue'])
        if cfg['scope']:
            cols.extend(cfg['scope'])
        if table == 'transactions':
            cols.append('position_id')
        for raw in con.execute(f'SELECT {", ".join(cols)} FROM {table}').fetchall():
            rec = dict(zip(cols, raw))
            pk = rec[cfg['pk']]
            symbol = rec[cfg['symbol']] or ''
            if not symbol:
                continue
            asset_type = rec[cfg['asset_type']]
            declared = rec.get(cfg['venue']) if cfg['venue'] else None
            # 流水自身没标类型时，回退到它挂的持仓（口径与写入侧一致）
            if table == 'transactions' and not asset_type and rec['position_id'] in pos_type:
                asset_type = pos_type[rec['position_id']]
            venue = venue_of_row(symbol, asset_type, declared)
            want = expected_symbol(symbol, venue)
            if want != symbol:
                scope = tuple(rec[c] for c in cfg['scope']) if cfg['scope'] else ()
                findings.append(
                    dict(
                        table=table,
                        pk=pk,
                        symbol=symbol,
                        expected=want,
                        venue=venue,
                        asset_type=asset_type,
                        scope=scope,
                    )
                )
    return findings


def audit_symbol_norm(con: sqlite3.Connection) -> list[dict]:
    """`positions.symbol_norm` 与「由 symbol + asset_type 重算的身份」不一致的行（#1662 后续）。

    `symbol_norm` 是**派生列**（构造见 `core/symbol_utils.symbol_identity`），判据即
    「重算值 == 库里存的值」。不一致只有两种成因：

    ① 列不存在 —— 迁移没跑（`core/migrations.py::migrate_positions_symbol_norm`）；
    ② 有人绕过 ORM 事件写库（`bulk_update_mappings` / 裸 SQL）—— 那正是唯一约束
       `uq_positions_ledger_symbol_norm` 会**静默失效**的形态，必须报出来。

    与 `audit()`（形态审计）分开：形态审计要改写 `symbol`，本审计只需按派生规则重算覆盖，
    修复动作不同、风险等级也不同，混在一起会让 `--apply` 的语义变模糊。
    """
    cols = [r[1] for r in con.execute('PRAGMA table_info("positions")')]
    if 'symbol_norm' not in cols:
        return [dict(pk=None, symbol='', expected='', actual='', why='symbol_norm 列不存在（迁移未跑）')]

    findings: list[dict] = []
    for rid, symbol, asset_type, actual in con.execute('SELECT id, symbol, type, symbol_norm FROM positions'):
        if not symbol:
            continue
        want = symbol_identity(symbol, asset_type)
        if (actual or '') != want:
            findings.append(dict(pk=rid, symbol=symbol, expected=want, actual=actual or '', why='与派生身份不一致'))
    return findings


def repair_symbol_norm(con: sqlite3.Connection) -> int:
    """按派生规则重算并覆盖 `positions.symbol_norm`（幂等）。返回受影响行数。"""
    n = 0
    for rid, symbol, asset_type in con.execute('SELECT id, symbol, type FROM positions').fetchall():
        if not symbol:
            continue
        con.execute(
            'UPDATE positions SET symbol_norm = ? WHERE id = ?',
            (symbol_identity(symbol, asset_type), rid),
        )
        n += 1
    return n


def duplicates(con: sqlite3.Connection, findings: list[dict]) -> list[dict]:
    """**同一业务作用域内**「归一后同码」的多行 —— 只有这类才是缺陷。

    跨账户同码（同一基金在多个 ledger 各持一份）是正常业务，绝不能合并。
    """
    want_of = {(f['table'], f['pk']): (f['expected'], f['scope']) for f in findings}
    groups: dict[tuple, dict] = {}
    for table, cfg in TABLES.items():
        if not cfg['merge']:
            continue
        cols = [cfg['pk'], cfg['symbol'], *cfg['scope']]
        for raw in con.execute(f'SELECT {", ".join(cols)} FROM {table}').fetchall():
            rec = dict(zip(cols, raw))
            pk, symbol = rec[cfg['pk']], rec[cfg['symbol']] or ''
            if not symbol:
                continue
            default = (symbol, tuple(rec[c] for c in cfg['scope']))
            want, scope = want_of.get((table, pk), default)
            key = (table, scope, want)
            groups.setdefault(key, dict(table=table, scope=scope, expected=want, pks=[]))
            groups[key]['pks'].append(pk)
    return [g for g in groups.values() if len(g['pks']) > 1]


def merge_rows(con: sqlite3.Connection, table: str, pks: list[int], canonical: str) -> dict:
    """把同作用域多行合并成一行：保留规范形态行，引用改指，删被并行。"""
    cfg = TABLES[table]
    colnames = columns(con, table)
    rows = con.execute(
        f'SELECT {", ".join(colnames)} FROM {table} WHERE {cfg["pk"]} IN ({",".join("?" * len(pks))})',
        pks,
    ).fetchall()
    dicts = [dict(zip(colnames, r)) for r in rows]
    keep = next((d for d in dicts if d[cfg['symbol']] == canonical), None)
    if keep is None:
        keep = max(dicts, key=lambda d: d[cfg['pk']])
    drops = [d for d in dicts if d[cfg['pk']] != keep[cfg['pk']]]

    # 作用域断言：防止把不同账户 / 不同市场的行误合并（本脚本最大风险点）
    for d in drops:
        for c in cfg['scope']:
            assert d[c] == keep[c], f'作用域不一致，拒绝合并: {c} {d[c]} != {keep[c]}'

    updates: dict[str, object] = {cfg['symbol']: canonical}
    if table == 'positions':
        total_qty = sum(int(d['quantity'] or 0) for d in dicts)
        # 成本按**份额加权**（整数域运算，避免 float 误差污染金融口径）
        weighted = sum(int(d['quantity'] or 0) * int(d['avg_price'] or 0) for d in dicts)
        updates['quantity'] = total_qty
        updates['avg_price'] = round(weighted / total_qty) if total_qty else int(keep['avg_price'] or 0)
        newest = max(dicts, key=lambda d: d[cfg['pk']])
        updates['current_price'] = int(newest['current_price'] or keep['current_price'] or 0)
        dates = [d['confirm_date'] for d in dicts if d['confirm_date']]
        if dates:
            updates['confirm_date'] = max(dates)
    else:
        # watchlist：规范行缺失的字段用被并行补齐（收藏 / 置顶 / 成本 等用户状态）
        for field in (
            'favorite',
            'is_pinned',
            'favorite_at',
            'pinned_at',
            'cost_price',
            'quantity',
            'notes',
            'add_reason',
            'name',
        ):
            if field in colnames and not keep[field]:
                for d in drops:
                    if d[field]:
                        updates[field] = d[field]
                        break

    assignments = ', '.join(f'{k} = ?' for k in updates)
    con.execute(
        f'UPDATE {table} SET {assignments} WHERE {cfg["pk"]} = ?',
        (*updates.values(), keep[cfg['pk']]),
    )
    for ref in ref_tables(con, table):
        for d in drops:
            con.execute(
                f'UPDATE "{ref}" SET {cfg["ref_col"]} = ? WHERE {cfg["ref_col"]} = ?',
                (keep[cfg['pk']], d[cfg['pk']]),
            )
    for d in drops:
        con.execute(f'DELETE FROM {table} WHERE {cfg["pk"]} = ?', (d[cfg['pk']],))
    return dict(kept=keep[cfg['pk']], dropped=[d[cfg['pk']] for d in drops], symbol=canonical, updates=updates)


def main() -> int:
    ap = argparse.ArgumentParser(description='#1662 symbol / venue 一致性审计与修复')
    ap.add_argument('--db', default=str(DEFAULT_DB), help='SQLite 路径（默认 backend/invest.db）')
    ap.add_argument('--apply', action='store_true', help='执行修复（默认只审计）')
    ap.add_argument('--merge', action='store_true', help='合并同作用域重复行（默认只报不动）')
    ap.add_argument('--json', action='store_true', help='以 JSON 输出审计结果')
    args = ap.parse_args()

    db_path = pathlib.Path(args.db)
    if not db_path.exists():
        print(f'数据库不存在: {db_path}', file=sys.stderr)
        return 2

    con = sqlite3.connect(f'file:{db_path.as_posix()}?mode=rw', uri=True)
    try:
        findings = audit(con)
        norm_findings = audit_symbol_norm(con)
        dups = duplicates(con, findings)
        dup_pks = {(d['table'], pk) for d in dups for pk in d['pks']}

        if args.json:
            print(
                json.dumps(
                    dict(db=str(db_path), findings=findings, duplicates=dups, norm_findings=norm_findings),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f'库: {db_path}')
            print(f'不合规行: {len(findings)}')
            for f in findings:
                mark = '重复' if (f['table'], f['pk']) in dup_pks else '改写'
                print(
                    f'  [{f["table"]}] id={f["pk"]:>6}  {f["symbol"]:<12} → {f["expected"]:<12}'
                    f' venue={f["venue"] or "(无)":<9} type={str(f["asset_type"]):<10}'
                    f' scope={f["scope"]}  ({mark})'
                )
            for d in dups:
                print(f'  重复组 [{d["table"]}] scope={d["scope"]} {d["expected"]}: ids={d["pks"]}')
            print(f'symbol_norm 不一致: {len(norm_findings)} 行')
            for n in norm_findings:
                print(
                    f'  [positions] id={n["pk"]}  symbol={n["symbol"]}  '
                    f'库里={n["actual"] or "(空)"} 应为={n["expected"] or "(空)"}  ({n["why"]})'
                )

        if not args.apply:
            print('\n（只读审计：未改动任何数据。加 --apply 执行修复）')
            return 1 if (findings or norm_findings) else 0

        if not findings and not norm_findings:
            print('\n无需修复。')
            return 0

        bpath = backup(db_path)
        print(f'\n已备份: {bpath}')

        groups = {(d['table'], tuple(d['scope']), d['expected']): d for d in dups}
        merged: list[dict] = []
        rewritten: list[dict] = []
        skipped: list[tuple[str, str, tuple, str]] = []
        handled: set[int] = set()

        # 1) 先处理「同作用域归一后同码」的重复组（每组只处理一次）
        for (table, scope, want), grp in groups.items():
            if not args.merge:
                skipped.append((table, want, tuple(scope), f'重复组（{len(grp["pks"])} 行）：需 --merge 才合并'))
                continue
            merged.append(merge_rows(con, table, grp['pks'], want))
            handled.update(grp['pks'])

        # 2) 再处理无冲突的单行前缀改写
        for f in findings:
            if (f['table'], f['pk']) in handled:
                continue
            if (f['table'], tuple(f['scope']), f['expected']) in groups:
                continue
            con.execute(
                f'UPDATE {f["table"]} SET {TABLES[f["table"]]["symbol"]} = ? WHERE {TABLES[f["table"]]["pk"]} = ?',
                (f['expected'], f['pk']),
            )
            rewritten.append(f)

        con.commit()
        print(f'合并重复: {len(merged)} 组')
        for m in merged:
            print(f'  {m["symbol"]}: 保留 id={m["kept"]} 删 {m["dropped"]} | {m["updates"]}')
        print(f'改写 symbol: {len(rewritten)} 行')
        for f in rewritten:
            print(f'  [{f["table"]}] id={f["pk"]} {f["symbol"]} → {f["expected"]}')
        if skipped:
            print(f'跳过（需人工）: {len(skipped)} 组')
            for table, want, scope, why in skipped:
                print(f'  [{table}] {want} scope={scope}：{why}')

        # 3) symbol_norm 是派生列：重算覆盖即可（幂等、无歧义，不涉及金额口径）
        if norm_findings:
            fixed = repair_symbol_norm(con)
            con.commit()
            print(f'symbol_norm 重算覆盖: {fixed} 行')

        remaining = audit(con)
        remaining_norm = audit_symbol_norm(con)
        print(
            f'\n复检：剩余形态不合规 {len(remaining)} 行 / symbol_norm 不一致 {len(remaining_norm)} 行'
            + (' ✅' if not remaining and not remaining_norm else '')
        )
        return 1 if (remaining or remaining_norm) else 0
    finally:
        con.close()


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置目标治理回填 **dry-run 报告**（#3031 / G3）。

只读扫描 ``assets`` / ``positions``，按冻结口径算出「哪些行会被改、旧值→新值、
依据是什么」，产出 CSV 给用户过目。**默认不写任何数据**；``--apply`` 在 G3 实改
放行后才允许使用，且必须同时给 ``--backup``（先落两表快照）。

判据（``docs/design/allocation-governance.md`` §三）：

    eligible = allocation_source == 'default'  AND  该行在「可投资资产端」成员集合内

两个条件缺一不可：只碰 default 是防覆盖用户手工配置（P0-7）；
限定成员集合是因为那 3 条 ``user`` 行（房子 stable / 借款应收 liquid）在新边界下
属「未纳入」，值要保留但**不参与分布**，更不该被回填。

规则唯一真相源是 ``backend/app/core/allocation_rules.py``；本脚本用 importlib
直接从文件加载（不 import ``app`` 包，避免拉起 flask/dotenv 依赖），
保证治理脚本与运行期代码用的是同一张规则表。

用法：

    python scripts/backfill_allocation.py --db backend/invest.db --csv /tmp/backfill.csv
    python scripts/backfill_allocation.py --db backend/invest.db --json /tmp/backfill.json

⚠️ 本机真库尚未执行 G1 迁移（``allocation_source`` 列还不存在）时，脚本进入
   **模拟模式**：按迁移将如何打标在内存里推来源，并在报告里显式标注 SIMULATED，
   绝不假装读到了真实列值。
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import pathlib
import sqlite3
import sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')


def load_rules(root: pathlib.Path):
    path = root / 'backend' / 'app' / 'core' / 'allocation_rules.py'
    if not path.is_file():
        raise SystemExit(f'找不到规则真相源：{path}')
    spec = importlib.util.spec_from_file_location('allocation_rules_truth', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in con.execute(f'pragma table_info("{table}")')}


def fetch(con: sqlite3.Connection, table: str, cols: set[str]) -> list[dict]:
    want = [
        'id',
        'name',
        'allocation',
        'allocation_source',
        'major_category',
        'type',
        'quantity',
        'amount',
    ]
    selected = [c for c in want if c in cols]
    if 'allocation' not in selected:
        return []
    quoted = ','.join(f'"{c}"' for c in selected)
    where = 'quantity > 0' if table == 'positions' and 'quantity' in cols else '1=1'
    return [dict(r) for r in con.execute(f'SELECT {quoted} FROM "{table}" WHERE {where}')]


def simulated_source(row: dict) -> str:
    """G1 迁移的存量打标规则（见 migrations.migrate_allocation_source_columns）。"""
    old = row.get('allocation')
    return 'user' if old and old != 'longterm' else 'default'


def evaluate(rows: list[dict], table: str, has_source_col: bool, rules, mode: str) -> tuple[list[dict], Counter]:
    out: list[dict] = []
    stats: Counter = Counter()
    for row in rows:
        stats['total'] += 1
        major = row.get('major_category') if table == 'assets' else 'investment'
        if table == 'assets' and major == 'liability':
            stats['liability_skipped'] += 1
            continue
        member = rules.is_allocation_member(major)
        if not member:
            stats['non_member'] += 1
            continue
        source = row.get('allocation_source') if has_source_col else simulated_source(row)
        if source is None:
            source = rules.SOURCE_DEFAULT
        if source != rules.SOURCE_DEFAULT:
            stats[f'source_{source}'] += 1
            continue
        old = row.get('allocation') or rules.DEFAULT_ALLOCATION
        asset_type = row.get('type') if table == 'positions' else None
        new = rules.derive_allocation(major, asset_type)
        if new is None or new == old:
            stats['no_change'] += 1
            continue
        stats['would_change'] += 1
        stats[f'{old}_to_{new}'] += 1
        amount_yuan = ''
        if table == 'assets' and row.get('amount') is not None:
            amount_yuan = f'{row["amount"] / 100:.2f}'
        out.append(
            {
                'table': table,
                'id': row.get('id'),
                'name': row.get('name') or '',
                'major_category': major or '',
                'asset_type': asset_type or '',
                'old_allocation': old,
                'new_allocation': new,
                'source': source,
                'mode': mode,
                'amount_yuan': amount_yuan,
                'reason': f'{major or "position"}/{asset_type or "-"} → {new}（规则表）',
            }
        )
    return out, stats


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='配置目标治理回填 dry-run（#3031 / G3，默认只读）')
    p.add_argument('--db', default='backend/invest.db')
    p.add_argument('--root', default=str(pathlib.Path(__file__).resolve().parents[1]))
    p.add_argument('--csv', default=None, help='导出逐行建议 CSV')
    p.add_argument('--json', default=None, help='导出聚合结论 JSON')
    p.add_argument('--apply', action='store_true', help='G3 实改放行后才可用；本轮禁止')
    p.add_argument('--backup', default=None, help='--apply 时必须给两表快照目录')
    args = p.parse_args(argv)

    if args.apply:
        print('[backfill] 本轮 G3 实改尚未放行（需先确认 dry-run 报告）。拒绝 --apply。', file=sys.stderr)
        return 2

    root = pathlib.Path(args.root).resolve()
    rules = load_rules(root)
    db = pathlib.Path(args.db).resolve()
    if not db.is_file():
        raise SystemExit(f'找不到数据库：{db}')
    con = sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        all_changes: list[dict] = []
        report: dict = {'db': str(db), 'tables': {}}
        for table in ('assets', 'positions'):
            cols = table_columns(con, table)
            has_source = 'allocation_source' in cols
            mode = 'REAL' if has_source else 'SIMULATED'
            rows = fetch(con, table, cols)
            changes, stats = evaluate(rows, table, has_source, rules, mode)
            all_changes.extend(changes)
            report['tables'][table] = {
                'mode': mode,
                'has_allocation_source_column': has_source,
                'stats': dict(sorted(stats.items())),
            }
            print(f'=== {table} [{mode}] ===')
            for k, v in sorted(stats.items()):
                print(f'  {k:<28} {v}')
            print()
        report['would_change_total'] = len(all_changes)
        report['by_transition'] = dict(Counter(f'{c["old_allocation"]}→{c["new_allocation"]}' for c in all_changes))
    finally:
        con.close()

    print('=== 汇总 ===')
    print(f'  建议变更行数：{len(all_changes)}')
    print(f'  旧→新分布：{report["by_transition"]}')
    print('  ⚠️ 负债行 skipping 必须 > 0 且绝不出现在变更清单；否则规则守卫失效。')
    liability_in_changes = [c for c in all_changes if c['major_category'] == 'liability']
    if liability_in_changes:
        print('[backfill] 严重：负债行出现在变更清单，拒绝出报告。', file=sys.stderr)
        return 1
    print('  [OK] 负债零命中。')
    print('  本脚本只读；G3 实改需 --apply + --backup，且必须先取得 dry-run 确认。')

    if args.csv:
        out = pathlib.Path(args.csv).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            'table',
            'id',
            'name',
            'major_category',
            'asset_type',
            'old_allocation',
            'new_allocation',
            'source',
            'mode',
            'amount_yuan',
            'reason',
        ]
        with out.open('w', encoding='utf-8-sig', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(all_changes)
        print(f'\n[backfill] 逐行建议已导出：{out}（{len(all_changes)} 行）')
    if args.json:
        out = pathlib.Path(args.json).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'[backfill] 聚合结论已导出：{out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

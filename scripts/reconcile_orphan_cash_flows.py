#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""账外孤儿类现金流水**只读核实**（#3031 / G0）。

对 ``position_id IS NULL AND asset_type IN ('money_fund','reverse_repo')`` 的流水
做一次可复现的对账：净额口径复现、跨账本重复扫描、来源元数据完整性统计，
并可选导出逐笔明细 CSV 供人工下钻。

WHY 单独成脚本：``LedgerCashLikeCard.vue`` 只给一个汇总数与一句「可能混有跨账本
重复导入」，既不说明判据也不留明细；而 G2/G4 是否放行这 46.5 万入五笔钱分母，
必须建立在**能逐笔复核**的记录上，不能靠一句 UI 文案。
「记录下来」= 结论写进 ``docs/working-notes/cash-like-orphan-flows-2026-11-10.md``
+ 本脚本随时重跑出明细，而不是把 222 行个人财务数据静态提交进仓库。

⚠️ 本脚本**只读**：sqlite 以 ``mode=ro`` 打开，不执行任何 UPDATE/DELETE/DDL。
   导出的 CSV 由调用方自行指定路径，默认不落盘。

口径真相源：``app.services.summary_service.orphan_flow_delta``（buy/deposit 正、
sell/withdraw 负、dividend/dividend_cash 进收益桶、dividend_tax 收益桶负）。
优先直接 import；若当前环境没有 app 包（例如只想在任意目录跑），会退到一份
**带显式告警**的镜像实现——绝不静默用镜像冒充同源。

用法：

    python scripts/reconcile_orphan_cash_flows.py
    python scripts/reconcile_orphan_cash_flows.py --db /path/to/invest.db --csv /tmp/flows.csv
    PYTHONPATH=backend python scripts/reconcile_orphan_cash_flows.py   # 直接调用真相源
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import pathlib
import sqlite3
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')

ORPHAN_ASSET_TYPES = ('money_fund', 'reverse_repo')
POSITIVE_TYPES = ('buy', 'deposit')
NEGATIVE_TYPES = ('sell', 'withdraw')
INCOME_TYPES = ('dividend', 'dividend_cash')
TAX_TYPES = ('dividend_tax',)
BUCKET_NET = 'net'
BUCKET_INCOME = 'income'

#: 与 ``summary_service`` 顶层同名常量一一对应；``verify_truth_constants`` 会静态比对，
#: 真相源一改而脚本没跟上就立刻红，绝不让镜像悄悄漂移。
TRUTH_CONSTANTS = {
    '_ORPHAN_FLOW_ASSET_TYPES': ORPHAN_ASSET_TYPES,
    '_ORPHAN_FLOW_POSITIVE_TYPES': POSITIVE_TYPES,
    '_ORPHAN_FLOW_NEGATIVE_TYPES': NEGATIVE_TYPES,
    '_ORPHAN_FLOW_INCOME_TYPES': INCOME_TYPES,
    '_ORPHAN_FLOW_TAX_TYPES': TAX_TYPES,
}


def verify_truth_constants(root: pathlib.Path) -> tuple[bool, str]:
    """静态解析真相源常量并逐项比对（不 import，避免拉起 Flask 依赖）。

    WHY 用 AST 而不是 import：``summary_service`` 会连带拉起 dotenv / flask / sqlalchemy，
    本机这些包未必齐（2026-11-10 实测 ``No module named 'dotenv'``）。只读源码字面量
    零依赖，且常量一改脚本立刻红——这才是「同源」的硬保障，而不是嘴上说同源。
    """
    src = root / 'backend' / 'app' / 'services' / 'summary_service.py'
    if not src.is_file():
        return False, f'找不到真相源 {src}（用 --root 指定仓库根）'
    try:
        tree = ast.parse(src.read_text(encoding='utf-8'))
    except SyntaxError as exc:
        return False, f'真相源解析失败：{exc}'
    found: dict[str, tuple] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in TRUTH_CONSTANTS:
                try:
                    found[target.id] = tuple(ast.literal_eval(node.value))
                except (ValueError, TypeError):
                    pass
    missing = sorted(set(TRUTH_CONSTANTS) - set(found))
    if missing:
        return False, f'真相源缺少常量：{missing}'
    mismatch = [f'{k} 真相源={found[k]} 脚本={v}' for k, v in TRUTH_CONSTANTS.items() if found[k] != tuple(v)]
    if mismatch:
        return False, '常量漂移：' + '; '.join(mismatch)
    return True, f'{len(TRUTH_CONSTANTS)} 组常量与 {src.relative_to(root).as_posix()} 逐项一致'


def _mirror_delta(txn_type, amount, is_income):
    """``orphan_flow_delta`` 的镜像（仅当 app 包不可用时），必须与之逐条保持一致。"""
    amount = amount or 0
    if txn_type in INCOME_TYPES:
        return BUCKET_INCOME, amount
    if txn_type in TAX_TYPES:
        return BUCKET_INCOME, -amount
    if txn_type in POSITIVE_TYPES:
        delta = amount
    elif txn_type in NEGATIVE_TYPES:
        delta = -amount
    else:
        return None
    return (BUCKET_INCOME if is_income else BUCKET_NET), delta


def load_delta():
    """优先调用服务层真相源；不可用时回退并显式告警。"""
    try:
        from app.services.summary_service import orphan_flow_delta  # type: ignore

        return orphan_flow_delta, 'app.services.summary_service.orphan_flow_delta（同源）'
    except ImportError as exc:  # 只兜依赖缺失；其余异常直接暴露，不吞（#2988 教训）
        print(f'[warn] 无法 import 服务层真相源（{type(exc).__name__}: {exc}）', file=sys.stderr)
        print('[warn] 本次使用脚本内镜像口径；变更 orphan_flow_delta 时务必同步本脚本。', file=sys.stderr)
        return _mirror_delta, '脚本内镜像（非同源，见上方告警）'


def fetch_rows(db_path: pathlib.Path) -> list[dict]:
    if not db_path.is_file():
        raise SystemExit(f'找不到数据库：{db_path}')
    con = sqlite3.connect(f'file:{db_path.as_posix()}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        placeholders = ','.join('?' for _ in ORPHAN_ASSET_TYPES)
        # #3089：已归置流水由持仓市值承接，不再属于账外类现金；旧库可能还没跑过
        # 加列迁移，此时显式告警而不是让脚本直接崩在「no such column」。
        columns = {r['name'] for r in con.execute('PRAGMA table_info(transactions)')}
        has_coverage = 'covered_position_id' in columns
        if not has_coverage:
            print(
                '[warn] 库里没有 covered_position_id 列，本次结论可能含已归置流水（请先启动一次应用以跑迁移）',
                file=sys.stderr,
            )
        covered = ' AND covered_position_id IS NULL' if has_coverage else ''
        sql = f'SELECT * FROM transactions WHERE position_id IS NULL AND asset_type IN ({placeholders}){covered}'
        return [dict(r) for r in con.execute(sql, ORPHAN_ASSET_TYPES)]
    finally:
        con.close()


def fingerprint(row: dict) -> tuple:
    """与 ``scan_cross_ledger_duplicates`` 一致：confirm_date + symbol + txn_type + amount。

    该扫描用的是 ``symbol_identity``（归一身份）；孤儿流水里 symbol 多为 NULL，
    这里保留字面量并**单独统计 symbol 缺失数**，缺失项本身列为「不可下钻」。
    """
    return (row.get('confirm_date'), row.get('symbol') or '', row.get('type'), row.get('amount'))


def analyse(rows: list[dict], delta) -> dict:
    net = income = 0
    by_ledger: dict = defaultdict(lambda: [0, 0])
    skipped: list[int] = []
    for r in rows:
        moved = delta(r.get('type'), r.get('amount'), r.get('is_income'))
        if moved is None:
            skipped.append(r['id'])
            continue
        bucket, cents = moved
        if bucket == BUCKET_NET:
            net += cents
            by_ledger[r.get('ledger_id')][0] += cents
        else:
            income += cents
            by_ledger[r.get('ledger_id')][1] += cents

    # 项目口径跨账本重复（与 scan_cross_ledger_duplicates 同样只认 success + 非空 ledger）
    groups: dict = defaultdict(list)
    for r in rows:
        if r.get('status') == 'success' and r.get('ledger_id'):
            groups[fingerprint(r)].append(r)
    cross = {k: v for k, v in groups.items() if len({x['ledger_id'] for x in v}) > 1}
    dup_same = {k: v for k, v in groups.items() if len(v) > 1 and len({x['ledger_id'] for x in v}) == 1}

    hashes: dict = defaultdict(list)
    for r in rows:
        if r.get('import_hash'):
            hashes[r['import_hash']].append(r)
    hash_dups = {k: v for k, v in hashes.items() if len(v) > 1}
    hash_cross = {k: v for k, v in hash_dups.items() if len({x['ledger_id'] for x in v}) > 1}

    odd = [r for r in rows if not r.get('trade_date') or not r.get('symbol')]

    def counter(key):
        return dict(Counter(r.get(key) for r in rows))

    return {
        'rows': len(rows),
        'net_cents': net,
        'income_cents': income,
        'total_cents': net + income,
        'by_ledger': {str(k): [v[0], v[1]] for k, v in by_ledger.items()},
        'skipped_ids': skipped,
        'status': counter('status'),
        'entry_status': counter('entry_status'),
        'source': counter('source'),
        'type': counter('type'),
        'asset_type': counter('asset_type'),
        'ledger': counter('ledger_id'),
        'no_confirm_date': sum(1 for r in rows if not r.get('confirm_date')),
        'no_trade_date': sum(1 for r in rows if not r.get('trade_date')),
        'no_symbol': sum(1 for r in rows if not r.get('symbol')),
        'no_import_hash': sum(1 for r in rows if not r.get('import_hash')),
        'trade_date_has_time': sum(1 for r in rows if r.get('trade_date') and len(str(r['trade_date'])) > 10),
        'cross_ledger_dup_groups': len(cross),
        'cross_ledger_dup_rows': sum(len(v) for v in cross.values()),
        'same_ledger_dup_groups': len(dup_same),
        'same_ledger_dup_rows': sum(len(v) for v in dup_same.values()),
        'import_hash_dup_groups': len(hash_dups),
        'import_hash_dup_rows': sum(len(v) for v in hash_dups.values()),
        'import_hash_cross_ledger_groups': len(hash_cross),
        'untraceable_rows': len(odd),
        'untraceable_gross_cents': sum(r.get('amount') or 0 for r in odd),
        'odd_sample': [
            {
                'id': r['id'],
                'ledger_id': r.get('ledger_id'),
                'type': r.get('type'),
                'trade_date': r.get('trade_date'),
                'confirm_date': r.get('confirm_date'),
                'symbol': r.get('symbol'),
                'amount_cents': r.get('amount'),
            }
            for r in odd[:12]
        ],
    }


def row_flags(r: dict, dup_keys: set) -> str:
    flags = []
    if not r.get('trade_date'):
        flags.append('no_trade_date')
    elif len(str(r['trade_date'])) > 10:
        flags.append('trade_date_has_time')
    if not r.get('symbol'):
        flags.append('no_symbol')
    if not r.get('source'):
        flags.append('no_source')
    if not r.get('import_hash'):
        flags.append('no_import_hash')
    if fingerprint(r) in dup_keys:
        flags.append('dup_fingerprint')
    return '|'.join(flags)


def write_csv(path: pathlib.Path, rows: list[dict], delta) -> None:
    dup_counter: Counter = Counter(fingerprint(r) for r in rows)
    dup_keys = {k for k, n in dup_counter.items() if n > 1}
    fields = [
        'id',
        'ledger_id',
        'trade_date',
        'confirm_date',
        'symbol',
        'asset_type',
        'type',
        'amount_yuan',
        'is_income',
        'entry_status',
        'status',
        'source',
        'import_hash',
        'delta_bucket',
        'delta_cents',
        'flags',
    ]
    with path.open('w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            moved = delta(r.get('type'), r.get('amount'), r.get('is_income'))
            bucket, cents = moved if moved else ('', 0)
            w.writerow(
                {
                    'id': r['id'],
                    'ledger_id': r.get('ledger_id'),
                    'trade_date': r.get('trade_date'),
                    'confirm_date': r.get('confirm_date'),
                    'symbol': r.get('symbol'),
                    'asset_type': r.get('asset_type'),
                    'type': r.get('type'),
                    'amount_yuan': f'{(r.get("amount") or 0) / 100:.2f}',
                    'is_income': r.get('is_income'),
                    'entry_status': r.get('entry_status'),
                    'status': r.get('status'),
                    'source': r.get('source'),
                    'import_hash': r.get('import_hash'),
                    'delta_bucket': bucket,
                    'delta_cents': cents,
                    'flags': row_flags(r, dup_keys),
                }
            )


def yuan(cents: int) -> str:
    return f'{cents / 100:,.2f}'


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='账外孤儿类现金流水只读核实（#3031 / G0）')
    p.add_argument('--db', default='backend/invest.db', help='只读打开的 SQLite 路径')
    p.add_argument('--root', default=str(pathlib.Path(__file__).resolve().parents[1]), help='仓库根（定位真相源常量）')
    p.add_argument('--csv', default=None, help='可选：导出逐笔明细 CSV 到指定路径（默认不落盘）')
    p.add_argument('--json', default=None, help='可选：导出聚合结论 JSON')
    args = p.parse_args(argv)

    ok, msg = verify_truth_constants(pathlib.Path(args.root).resolve())
    print(f'[reconcile] 常量同源校验：{msg}')
    if not ok:
        print('[reconcile] 校验失败，拒绝用可能漂移的口径出结论。', file=sys.stderr)
        return 1

    delta, delta_src = load_delta()
    rows = fetch_rows(pathlib.Path(args.db).resolve())
    if not rows:
        print('[reconcile] 未找到孤儿类现金流水，无可核实内容。')
        return 0
    a = analyse(rows, delta)

    print(f'[reconcile] 口径来源：{delta_src}')
    print(f'[reconcile] DB：{args.db}（只读）  流水行数：{a["rows"]}')
    print()
    print('=== 净额复现（分 / 元） ===')
    print(f'  本金净额   {a["net_cents"]:>12} 分 = ¥{yuan(a["net_cents"])}')
    print(f'  收益桶     {a["income_cents"]:>12} 分 = ¥{yuan(a["income_cents"])}')
    print(f'  合计       {a["total_cents"]:>12} 分 = ¥{yuan(a["total_cents"])}   ← 应与 /api/summary/cash-like/ 一致')
    print(f'  不进桶行数 {len(a["skipped_ids"])}')
    for lid, (n, i) in a['by_ledger'].items():
        print(f'  ledger {lid}: 本金 ¥{yuan(n)} / 收益 ¥{yuan(i)}')
    print()
    print('=== 重复扫描 ===')
    print(f'  跨账本重复组（项目指纹）        {a["cross_ledger_dup_groups"]} 组 / {a["cross_ledger_dup_rows"]} 行')
    print(f'  同账本成对行                    {a["same_ledger_dup_groups"]} 组 / {a["same_ledger_dup_rows"]} 行')
    print(
        f'  import_hash 重复 / 其中跨账本   {a["import_hash_dup_groups"]} 组 / {a["import_hash_cross_ledger_groups"]} 组'
    )
    print(f'  status 分布                     {a["status"]}   ← 全 success 才说明对账中心确实扫到')
    print(f'  confirm_date 缺失               {a["no_confirm_date"]}')
    print()
    print('=== 来源可追溯性（真正的问题） ===')
    print(f'  trade_date 缺失                 {a["no_trade_date"]}')
    print(f'  symbol 缺失                    {a["no_symbol"]}')
    print(f'  import_hash 缺失               {a["no_import_hash"]}')
    print(f'  trade_date 带时间（格式混杂）  {a["trade_date_has_time"]}')
    print(f'  source 分布                    {a["source"]}')
    print(f'  entry_status 分布              {a["entry_status"]}')
    print(f'  不可下钻行 / 流水毛毛额         {a["untraceable_rows"]} 行 / ¥{yuan(a["untraceable_gross_cents"])}')
    print(f'  type 分布                      {a["type"]}')
    print(f'  asset_type 分布                {a["asset_type"]}')
    print(f'  ledger 分布                    {a["ledger"]}')
    print()
    if a['odd_sample']:
        print('=== 不可下钻行样例（前 12） ===')
        for s in a['odd_sample']:
            print(
                f'  id={s["id"]} ledger={s["ledger_id"]} {s["type"]} trade={s["trade_date"]!r} '
                f'confirm={s["confirm_date"]!r} symbol={s["symbol"]!r} ¥{(s["amount_cents"] or 0) / 100:.2f}'
            )
    print()
    print('=== 结论 ===')
    if a['cross_ledger_dup_groups'] == 0 and a['import_hash_cross_ledger_groups'] == 0:
        print('  跨账本重复：无。UI「可能混有跨账本重复导入」在本库数据上不成立。')
    else:
        print('  跨账本重复：存在，须先处理再谈归置。')
    print(f'  仍不建议直接入「活钱」：{a["untraceable_rows"]} 行来源不可追溯、无法逐笔下钻。')
    print('  是否放行进入五笔钱分母，需用户确认；本脚本不修改任何数据。')

    if args.csv:
        out = pathlib.Path(args.csv).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        write_csv(out, rows, delta)
        print(f'\n[reconcile] 逐笔明细已导出：{out}（{len(rows)} 行）')
    if args.json:
        out = pathlib.Path(args.json).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(a, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'[reconcile] 聚合结论已导出：{out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

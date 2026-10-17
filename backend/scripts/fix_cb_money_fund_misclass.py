# -*- coding: utf-8 -*-
"""一次性修复：可转债被旧版代码归一规则错标为货币基金的存量脏流水。

背景
----
历史导入（2023-04 ~ 2024-03 批次）经同花顺账本解析入库时，旧版
``StockCodeNormalizer.SPECIAL_CODES`` 把 ``^11[1-9]\\d{3}$``（沪市可转债代码段）
误判为「深市货币基金」，导致 43 只可转债的流水被写成：

  - ``asset_type='money_fund'``、``symbol=NULL``、``quantity=0``、``entry_status=NULL``
  - 走「现金管理产品」提交分支（``orchestrator_commit.py``），不建持仓

显示层 ``summary_service.orphan_cash_like_breakdown`` 依据 ``asset_type`` 聚合，
这些转债因此出现在「类现金 → 账外孤儿流水」明细里（账户 12 实测 43 只）。

该 bug 已于 #1661（commit 88774cc06，2026-09-23）在归一层修复——**新导入不再产生**
脏数据；本脚本只清理**存量**脏行，不触碰任何其它行。

判定口径（与排查阶段实证一致，见 docs/working-notes 与 issue 讨论）
----------------------------------------------------------------
1. ``asset_type='money_fund'`` 且 ``position_id IS NULL`` 且 ``symbol`` 为空；
2. ``position_name`` 精确命中 ``securities.name``（**禁用** ``LIKE '%转债%'`` 模糊匹配）；
3. 命中名录的 symbol（``SH/SZ`` 前缀式，如 ``SH113066``）落在转债代码段
   ``SH11xxxx`` / ``SZ12xxxx``；
4. ``N平煤转`` 走显式别名表 → ``平煤转债``（N 前缀是上市首日临时简称，不在名录；
   txn#455/457、#1760/1762 与平煤转债 buy/sell 配对实证）；
5. 同名多 symbol（巨星转债 / 益丰转债）**跳过并报告**，不替使用者猜。

修复动作（严格最小面）
--------------------
- 仅改 ``asset_type: 'money_fund' -> 'bond'`` + 回填 ``symbol = securities.symbol``；
- **不删行**、不改金额 / type / ledger_id / position_id / trade_date / quantity / entry_status。

安全设计
--------
- **必须显式指定 ``--db``**：脚本用标准库 sqlite3 直连给定文件，不导入应用会话
  ——避免环境里配了 ``SUPABASE_DATABASE_URL`` 时误连生产。
- **默认 dry-run**：只打印将改动的行；写库需显式 ``--apply``。
- **apply 自动落回滚 SQL**（默认写到库旁 ``data/backup_cb_money_fund_<时间戳>.sql``，
  逐行反向 UPDATE，可精确回滚）；``--rollback-out`` 可改路径。
- **apply 后四重断言**，任一失败即整体回滚、非零退出：
  ① 修复行全部已是 ``bond`` 且 symbol 正确；② ``money_fund`` 总数减少量 == 修复数；
  ③ 名录外真货基（银河水星现金添利 / 水星1号等）名字计数逐字不变；
  ④ 重扫判定口径，剩余命中恰好等于跳过的歧义行。

用法
----
  cd backend
  python scripts/fix_cb_money_fund_misclass.py --db invest.db            # dry-run
  python scripts/fix_cb_money_fund_misclass.py --db invest.db --apply    # 写库
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

#: 上市首日临时简称 → 名录名。只放**人工实证过配对关系**的条目，不做任何模糊推广。
NAME_ALIASES = {'N平煤转': '平煤转债'}

#: 名录 symbol 必须落在转债代码段：沪市 11xxxx / 深市 12xxxx（SH/SZ 前缀式）。
BOND_SYMBOL_RE = re.compile(r'^(?:SH|SZ)(?:11|12)\d{4}$')


@dataclass
class FixItem:
    """一条待修流水：错标 money_fund → bond。"""

    txn_id: int
    ledger_id: int
    position_name: str  #: 流水原始名（含未归一形态，如 N平煤转）
    trade_date: str | None
    txn_type: str
    amount: int
    sec_symbol: str  #: 回填目标，如 SH113066


@dataclass
class ScanResult:
    fixes: list[FixItem] = field(default_factory=list)
    #: (position_name, 候选 symbols, txn_ids) —— 同名多 symbol，不猜
    ambiguous: list[tuple[str, tuple[str, ...], list[int]]] = field(default_factory=list)
    #: 名录外真货基等「禁碰」行：(position_name, 条数)
    untouched: Counter = field(default_factory=Counter)
    alias_hits: Counter = field(default_factory=Counter)
    mf_total_before: int = 0


def scan(cur: sqlite3.Cursor) -> ScanResult:
    """扫描存量脏行，产出修复清单。真货基与歧义行一律不进 fixes。"""
    result = ScanResult()

    sec_by_name: dict[str, list[str]] = {}
    for name, symbol in cur.execute('SELECT name, symbol FROM securities'):
        sec_by_name.setdefault(name, []).append(symbol)

    rows = cur.execute(
        'SELECT id, ledger_id, position_name, trade_date, type, amount'
        ' FROM transactions'
        " WHERE asset_type='money_fund' AND position_id IS NULL"
        " AND (symbol IS NULL OR symbol='')"
    ).fetchall()

    amb_by_name: dict[str, list[int]] = {}
    amb_symbols: dict[str, tuple[str, ...]] = {}
    for txn_id, ledger_id, pos_name, trade_date, txn_type, amount in rows:
        sec_name = NAME_ALIASES.get(pos_name or '', pos_name or '')
        cands = tuple(sorted(s for s in sec_by_name.get(sec_name, []) if BOND_SYMBOL_RE.match(s)))
        if not cands:
            # 名录外（银河水星现金添利 / 水星1号…）或非转债代码段：真货基，禁碰
            result.untouched[pos_name or ''] += 1
            continue
        if len(cands) > 1:
            amb_by_name.setdefault(sec_name, []).append(txn_id)
            amb_symbols[sec_name] = cands
            continue
        if sec_name != (pos_name or ''):
            result.alias_hits[f'{pos_name} → {sec_name}'] += 1
        result.fixes.append(
            FixItem(
                txn_id=txn_id,
                ledger_id=ledger_id,
                position_name=pos_name or '',
                trade_date=trade_date,
                txn_type=txn_type,
                amount=amount,
                sec_symbol=cands[0],
            )
        )

    for name, txn_ids in sorted(amb_by_name.items()):
        result.ambiguous.append((name, amb_symbols[name], sorted(txn_ids)))

    result.mf_total_before = cur.execute("SELECT COUNT(*) FROM transactions WHERE asset_type='money_fund'").fetchone()[
        0
    ]
    return result


def apply_fixes(cur: sqlite3.Cursor, fixes: list[FixItem]) -> None:
    """逐行带守卫条件 UPDATE：并发下若行已被改动（rowcount != 1）立即抛错回滚。"""
    for it in fixes:
        cur.execute(
            "UPDATE transactions SET asset_type='bond', symbol=?"
            " WHERE id=? AND asset_type='money_fund' AND (symbol IS NULL OR symbol='')",
            (it.sec_symbol, it.txn_id),
        )
        if cur.rowcount != 1:
            raise RuntimeError(f'txn#{it.txn_id} 守卫更新失败（rowcount={cur.rowcount}），已回滚')


def emit_rollback_sql(fixes: list[FixItem], mode: str) -> str:
    """生成正向 / 反向 SQL 文本。反向段可精确回滚本次修复（恢复 money_fund + symbol=NULL）。"""
    lines = [
        '-- 可转债错标货币基金修复（fix_cb_money_fund_misclass.py 生成）',
        f'-- mode: {mode}  rows: {len(fixes)}',
        '-- 本文件不会被脚本执行。反向段用于回滚本次修复。',
        '',
        '-- ── 反向（回滚：恢复 asset_type=money_fund、symbol=NULL）──',
    ]
    for it in fixes:
        lines.append(
            f"UPDATE transactions SET asset_type='money_fund', symbol=NULL"
            f" WHERE id={it.txn_id} AND asset_type='bond' AND symbol='{it.sec_symbol}';"
            f'  -- {it.position_name} ledger={it.ledger_id}'
        )
    return '\n'.join(lines) + '\n'


def verify(cur: sqlite3.Cursor, fixes: list[FixItem], result: ScanResult) -> None:
    """apply 后四重断言，任一失败抛 RuntimeError（调用方负责回滚）。"""
    ids = [it.txn_id for it in fixes]
    ph = ','.join('?' * len(ids))
    ok = cur.execute(
        f"SELECT COUNT(*) FROM transactions WHERE id IN ({ph}) AND asset_type='bond'",
        ids,
    ).fetchone()[0]
    if ok != len(fixes):
        raise RuntimeError(f'断言①失败：{ok}/{len(fixes)} 行已是 bond')

    bad_symbol = cur.execute(
        f'SELECT COUNT(*) FROM transactions WHERE id IN ({ph})'
        " AND (symbol IS NULL OR symbol NOT LIKE 'SH%' AND symbol NOT LIKE 'SZ%')",
        ids,
    ).fetchone()[0]
    if bad_symbol:
        raise RuntimeError(f'断言①失败：{bad_symbol} 行 symbol 未回填')

    mf_after = cur.execute("SELECT COUNT(*) FROM transactions WHERE asset_type='money_fund'").fetchone()[0]
    if mf_after != result.mf_total_before - len(fixes):
        raise RuntimeError(f'断言②失败：money_fund 总数 {result.mf_total_before} → {mf_after}，期望减少 {len(fixes)}')

    untouched_after = Counter(
        dict(
            cur.execute(
                'SELECT position_name, COUNT(*) FROM transactions'
                " WHERE asset_type='money_fund' AND position_id IS NULL"
                " AND (symbol IS NULL OR symbol='') GROUP BY position_name"
            )
        )
    )
    for name, count in result.untouched.items():
        if untouched_after.get(name, 0) != count:
            raise RuntimeError(f'断言③失败：禁碰行 {name!r} 条数 {count} → {untouched_after.get(name, 0)}')

    residual = scan(cur)
    residual_amb = {(name, tuple(txn_ids)) for name, _syms, txn_ids in residual.ambiguous}
    expected_amb = {(name, tuple(txn_ids)) for name, _syms, txn_ids in result.ambiguous}
    if residual.fixes:
        raise RuntimeError(f'断言④失败：重扫仍有 {len(residual.fixes)} 条待修（应为 0）')
    if residual_amb != expected_amb:
        raise RuntimeError('断言④失败：残余歧义集合与跳过清单不一致')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='修复可转债错标为货币基金的存量脏流水')
    parser.add_argument(
        '--db',
        required=True,
        help='SQLite 数据库路径（必填；脚本直连该文件，不走应用会话工厂）',
    )
    parser.add_argument('--apply', action='store_true', help='真正写库（默认 dry-run）')
    parser.add_argument(
        '--rollback-out',
        default=None,
        help='回滚 SQL 输出路径（默认库旁 data/backup_cb_money_fund_<时间戳>.sql）',
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f'[错误] 数据库不存在：{db_path}', file=sys.stderr)
        return 2

    mode = 'apply' if args.apply else 'dry-run'
    # dry-run 以只读模式打开，物理上不可能写库；--apply 才开读写连接
    uri = db_path.resolve().as_uri() + ('?mode=ro' if not args.apply else '')
    con = sqlite3.connect(uri, uri=True)
    try:
        cur = con.cursor()
        result = scan(cur)
        fixes = sorted(result.fixes, key=lambda it: (it.ledger_id, it.txn_id))

        print(f'[{mode}] db={db_path.resolve()}')
        by_ledger = Counter(it.ledger_id for it in fixes)
        print(f'  待修：{len(fixes)} 条 {dict(sorted(by_ledger.items()))}')
        for alias, n in result.alias_hits.items():
            print(f'  [别名] {alias}：{n} 条')
        print(f'  [跳过-歧义] {len(result.ambiguous)} 个名字（同名多 symbol，不猜）：')
        for name, symbols, txn_ids in result.ambiguous:
            print(f'      {name}（{" | ".join(symbols)}）：txn{txn_ids}')
        untouched_n = sum(result.untouched.values())
        print(f'  [禁碰] 名录外真货基等 {untouched_n} 条，逐名字计数：')
        for name, n in result.untouched.most_common():
            print(f'      {name}：{n}')

        if not fixes:
            print('  无可修行，数据库已干净。')
            return 0

        if not args.apply:
            print('[dry-run] 未改动数据库（加 --apply 才写库）')
            return 0

        rollback_path = (
            Path(args.rollback_out)
            if args.rollback_out
            else db_path.parent / 'data' / f'backup_cb_money_fund_{time.strftime("%Y%m%d_%H%M%S")}.sql'
        )
        try:
            apply_fixes(cur, fixes)
            verify(cur, fixes, result)
        except Exception as exc:  # noqa: BLE001  一次性脚本：任何失败整体回滚
            con.rollback()
            print(f'[错误] 写库失败，已回滚：{exc}', file=sys.stderr)
            return 1
        con.commit()
        rollback_path.parent.mkdir(parents=True, exist_ok=True)
        rollback_path.write_text(emit_rollback_sql(fixes, mode), encoding='utf-8', newline='\n')
        print(f'[apply] 已修复 {len(fixes)} 条流水，四重断言全部通过')
        print(f'[apply] 回滚 SQL：{rollback_path}')
        return 0
    finally:
        con.close()


if __name__ == '__main__':
    raise SystemExit(main())

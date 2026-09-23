# -*- coding: utf-8 -*-
"""一次性修复：补挂回历史遗留的孤儿货基 / 逆回购流水（#1657）。

背景
----
`#863` 口径 A 互斥不变式：同一资金同一 `(ledger_id, symbol)` 只能有一种表达——
**持仓** 或 **孤儿流水净额**，不可并存。写入层建仓时会调
`position_service._reattach_orphan_flows` 把同 key 的孤儿流水挂回持仓。

但库里存在两类历史行：建仓发生在该机制启用之前、或建仓走了不经挂回的导入路径；
另有 `is_money_fund` 冗余列历史未回填（本机 pos[26] / pos[445] 为货基却为 0），
使「以该列作闸门」的写法漏挂。结果是同一 `(ledger, symbol)` 既有持仓、又有
`position_id IS NULL` 的货基流水，**同一笔钱被算两遍**。

本脚本按**运行时同一函数** `position_service.find_orphan_cash_flows` 扫全库补挂
——匹配口径只有一处实现，脚本不会与写入层漂移（#1657 复审的原始缺陷正是两处口径不一致：
脚本用 `symbol` 精确相等，`SZ001937` ↔ `001937` 这类跨形态组合被静默漏挂）。

安全设计
--------
- **必须显式指定 `--db`，无默认值**：脚本自建 SQLite 引擎，**刻意不复用 `SessionLocal`**
  ——后者是按 domain 晚绑定的路由会话工厂，环境里配了 `SUPABASE_DATABASE_URL` 即直连
  生产 PG，一次性脚本用它有误改生产的风险。（与 #1554 / #950 脚本的 CLI 惯例一致。）
- **默认 dry-run**：只打印将改动的 `txn.id` 与目标持仓，写库需显式 `--apply`。
- **`--rollback-out`**：输出逐行正向 / 反向 SQL（反向即 `position_id = NULL`），
  可精确回滚——比 1.2G 全库快照省，且可追溯。
- 多个持仓共享同一 `(ledger, family, 归一化代码)` 时**跳过并报告**，不替使用者做选择。

用法
----
  cd backend
  pdm run python scripts/fix_orphan_money_fund_reattach.py --db invest.db
  pdm run python scripts/fix_orphan_money_fund_reattach.py --db invest.db --apply
      --rollback-out rollback_1657.sql
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.domains.positions.models import Position  # noqa: E402
from app.services.fund_utils import normalize_fund_code  # noqa: E402
from app.services.position_service import (  # noqa: E402
    _reattach_orphan_flows,
    find_orphan_cash_flows,
)


@dataclass
class ReattachTarget:
    """一个待补挂目标：某个持仓 + 将要挂回它名下的孤儿流水。"""

    position_id: int
    ledger_id: int
    family_id: int
    position_symbol: str
    #: (txn_id, symbol, amount_cents)
    orphan_txns: list[tuple[int, str, int]] = field(default_factory=list)


@dataclass
class ScanResult:
    targets: list[ReattachTarget] = field(default_factory=list)
    #: (pos_id, code, 同 key 持仓数)
    skipped_ambiguous: list[tuple[int, str, int]] = field(default_factory=list)
    skipped_no_ledger: int = 0


def open_session(db_path: Path) -> Session:
    """自建只指向给定 SQLite 文件的引擎 / 会话——刻意不复用应用会话工厂（见模块 docstring）。"""
    engine = create_engine(f'sqlite:///{db_path.as_posix()}')
    return sessionmaker(bind=engine, future=True)()


def scan(db: Session) -> ScanResult:
    """扫描全部持仓，按运行时同一函数找出各自名下待挂回的孤儿现金等价物流水。

    归一化后拿不到 6 位数字的 symbol（非基金代码）不参与——`find_orphan_cash_flows`
    对这类返回空，天然无候选。同一 (ledger, family, 代码) 命中多个持仓时不猜，
    进 `skipped_ambiguous` 交人工判定。
    """
    result = ScanResult()
    groups: dict[tuple[int, int, str], list[Position]] = {}
    for pos in db.query(Position).all():
        if pos.ledger_id is None:
            result.skipped_no_ledger += 1
            continue
        code = normalize_fund_code(pos.symbol or '')
        if not code:
            continue
        groups.setdefault((pos.ledger_id, pos.family_id, code), []).append(pos)

    for (_ledger_id, _family_id, code), positions in sorted(groups.items()):
        if len(positions) > 1:
            result.skipped_ambiguous.append((positions[0].id, code, len(positions)))
            continue
        pos = positions[0]
        flows = sorted(
            find_orphan_cash_flows(db, pos.ledger_id, pos.symbol, pos.family_id),
            key=lambda t: t.id,
        )
        if not flows:
            continue
        result.targets.append(
            ReattachTarget(
                position_id=pos.id,
                ledger_id=pos.ledger_id,
                family_id=pos.family_id,
                position_symbol=pos.symbol,
                orphan_txns=[(t.id, t.symbol, t.amount) for t in flows],
            )
        )
    return result


def apply_targets(db: Session, targets: list[ReattachTarget]) -> int:
    """真正写库：调**运行时同一函数**挂回，使脚本与写入层行为逐字一致。

    写完后逐目标复检「剩余孤儿数 == 0」，不为 0 即抛错整体回滚——不留下「报成功但没改干净」。
    """
    for t in targets:
        _reattach_orphan_flows(db, t.ledger_id, t.position_symbol, t.position_id, t.family_id)
    db.flush()

    leftover = [
        (t.position_id, len(find_orphan_cash_flows(db, t.ledger_id, t.position_symbol, t.family_id))) for t in targets
    ]
    dirty = [pid for pid, n in leftover if n]
    if dirty:
        raise RuntimeError(f'补挂回后仍有孤儿的 pos_id={dirty}')

    db.commit()
    return sum(len(t.orphan_txns) for t in targets)


def emit_sql(targets: list[ReattachTarget]) -> str:
    """生成正向 / 反向 SQL 文本。**不会被脚本执行**，仅供人工复核与回滚。"""
    lines = [
        '-- #1657 补挂回候选 SQL（由 fix_orphan_money_fund_reattach.py 生成）',
        '-- 本文件不会被脚本执行。反向段可用于回滚本次补挂回。',
        '',
        '-- ── 正向：--apply 已执行的等价语句 ──',
    ]
    for t in targets:
        for txn_id, symbol, _amount in t.orphan_txns:
            lines.append(
                f'UPDATE transactions SET position_id = {t.position_id} '
                f'WHERE id = {txn_id} AND position_id IS NULL;  -- {symbol}'
            )
    lines += ['', '-- ── 反向（回滚）──']
    for t in targets:
        for txn_id, symbol, _amount in t.orphan_txns:
            lines.append(f'UPDATE transactions SET position_id = NULL WHERE id = {txn_id};  -- {symbol}')
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='补挂回历史孤儿货基 / 逆回购流水（#1657）')
    parser.add_argument(
        '--db',
        required=True,
        help='SQLite 数据库路径（必填；脚本自建引擎，不走应用会话工厂，避免误连生产）',
    )
    parser.add_argument('--apply', action='store_true', help='真正写库（默认 dry-run，只打印）')
    parser.add_argument(
        '--rollback-out',
        default=None,
        help='把正向 / 反向 SQL 写入该文件（不会被执行）',
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f'[错误] 数据库不存在：{db_path}', file=sys.stderr)
        return 2

    mode = 'apply' if args.apply else 'dry-run'
    db = open_session(db_path)
    try:
        result = scan(db)
        total_txn = sum(len(t.orphan_txns) for t in result.targets)

        print(f'[{mode}] db={db_path.resolve()}')
        print(f'  待补挂：{len(result.targets)} 个 (ledger, family, symbol) 分组 / {total_txn} 条流水')
        for t in result.targets:
            print(f'  -> pos_id={t.position_id} ledger={t.ledger_id} family={t.family_id} symbol={t.position_symbol}')
            for txn_id, symbol, amount in t.orphan_txns:
                print(f'       txn#{txn_id} symbol={symbol} amount={amount} 分')
        for pos_id, code, n in result.skipped_ambiguous:
            print(f'  [跳过] 代码 {code} 对应 {n} 个持仓，需人工判定（示例 pos_id={pos_id}）')
        if result.skipped_no_ledger:
            print(f'  [跳过] {result.skipped_no_ledger} 个持仓无 ledger_id，不可能有同 key 孤儿流水')

        if args.rollback_out:
            Path(args.rollback_out).write_text(emit_sql(result.targets), encoding='utf-8', newline='\n')
            print(f'  已写出正向 / 反向 SQL：{args.rollback_out}')

        if not result.targets:
            print('  无遗留孤儿货基流水，数据库已干净。')
            return 0

        if not args.apply:
            print('[dry-run] 未改动数据库（加 --apply 才写库）')
            return 0

        try:
            fixed = apply_targets(db, result.targets)
        except Exception as exc:  # noqa: BLE001  一次性脚本：任何失败都必须整体回滚并给出可读原因
            db.rollback()
            print(f'[错误] 写库失败，已回滚：{exc}', file=sys.stderr)
            return 1
        print(f'[apply] 已补挂回 {fixed} 条流水，逐目标复检剩余孤儿 = 0')
        return 0
    finally:
        db.close()


if __name__ == '__main__':
    raise SystemExit(main())

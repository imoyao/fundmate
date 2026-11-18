# -*- coding: utf-8 -*-
"""一次性修正「卖出已对冲、份额却仍挂着」的幽灵持仓（#3127 存量，真库 104 条）。

## 背景（已实证，勿再推断）

08-29 导入时同一标的的买腿带 `SZ128101`、卖腿 `symbol` 为空；11-15 09:14 的
`dangling_ref_rebuild` 按 `(ledger, symbol)` 分组，卖腿自成一组且被 `no_symbol` 挡住
⇒ **只拿买入腿**重建出 270 张；10:28 `enrich` 把卖腿补码、`reattach` 挂回目标持仓，
而回补按契约只改 `position_id`、不重算份额 ⇒ 净额 0 却仍 `active` + 270 张。

真库 2026-11-15 实测：**104 条**同形态（95 条由该次重建造出），账本 12 占 97 条，
合计虚增账面市值 ≈ **64.4 万元**。

## 判据（与重算入口同源，不另写一套）

对每条 `ownership_status='active'` 且 `quantity>0` 的持仓，用
`compute_anchored_state`（份额派生的**唯一**入口，含快照锚点）算「应有份额」：

- 应有份额 **> 0** ⇒ 不在本脚本范围（可能是「净额 > 0 但份额 ≠ 净额」那 29 条，
  口径不同，交持仓页「按流水重算份额」逐条处理）；
- 应有份额 **≤ 0** 且该持仓**至少有一条份额级流水**（`quantity != 0`）⇒ 本脚本的候选，
  走 `recompute_with_audit`（同一重算入口 + 写审计），结局是「标记清仓、行保留」。

两类必须排除，否则会误伤：

- **只有金额流水**（货币基金按 `amount` 记账、`quantity` 恒 0）⇒ 派生份额天然为 0，
  不是「卖完了」，按「无份额流水」跳过；
- **完全无流水**的持仓 ⇒ 重算会**删掉空壳行**，这不是本 bug 的形态，跳过（有快照锚点的
  持仓派生也不会为 0，不会被误判）。

## 安全约束

- 默认 **dry-run**，只打印计划改动；`--apply` 才写；
- `--apply` 前把 sqlite 库文件整库备份并打印路径；
- 每修一条都写 `adjustment_logs`（action=`position_recompute`，含改前 / 改后），
  单条失败不影响已修完的（逐条 `commit`），失败条目最后列出来。

用法：
    python scripts/fix_phantom_position_shares.py                    # 全库 dry-run
    python scripts/fix_phantom_position_shares.py --symbol SZ128101  # 只看某只
    python scripts/fix_phantom_position_shares.py --apply            # 真正修
"""

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# 让脚本能 import 项目包。**用 append 而不是 insert(0)**：跨 worktree 时
# PYTHONPATH 指的代码必须优先于本文件所在目录，否则永远量的是本地那份。
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

# 本脚本只读 / 一次性写数据，不监听端口，不该与 dev server 抢单实例锁
os.environ.setdefault('APP_INSTANCE_GUARD', '0')

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

_REASON = '存量修复(#3127)：流水净额≤0 但持仓仍 active 且份额>0'


def _backup(url: str) -> Path | None:
    """sqlite 文件库整库备份；非文件库（Turso 等）不备份，返回 None 由调用方如实告知。

    相对路径按 **cwd** 解析（引擎就是这么解析 `sqlite:///./invest.db` 的），不能按脚本目录
    ——跨 worktree 跑时脚本在 worktree、库在主仓 cwd，按脚本目录会找不到文件而**静默跳过备份**。
    """
    if not url.startswith('sqlite'):
        return None
    raw = url.split('sqlite:///', 1)[-1]
    src = Path(raw)
    if not src.is_absolute():
        src = Path.cwd() / src
    if not src.exists():
        raise SystemExit(f'备份失败：找不到库文件 {src}（相对路径按 cwd 解析），已中止、未写任何数据')
    dst = src.with_name(f'backup_{src.stem}_{datetime.now():%Y%m%d_%H%M%S}{src.suffix}')
    shutil.copy2(src, dst)
    return dst


def main() -> int:
    parser = argparse.ArgumentParser(description='修正「卖完未清仓」的幽灵持仓（#3127）')
    parser.add_argument('--apply', action='store_true', help='真正写入（默认 dry-run）')
    parser.add_argument('--family', type=int, default=None, help='只处理指定家庭')
    parser.add_argument('--symbol', default=None, help='只处理指定标的（支持裸码/带前缀）')
    parser.add_argument('--limit', type=int, default=20, help='dry-run 时最多打印多少条明细')
    args = parser.parse_args()

    from app.core.database import get_db
    from app.core.db_factory import app_database_url
    from app.core.money import Money
    from app.domains.positions.models import Position
    from app.domains.transactions.models import Transaction
    from app.main import create_app
    from app.services.position_recompute_entry import recompute_with_audit
    from app.services.position_service import compute_anchored_state

    print(f'代码来源: {__import__("app").__file__}')
    print(f'目标库  : {app_database_url()}')
    print(f'模式    : {"APPLY（写库）" if args.apply else "DRY-RUN（只打印）"}\n')

    app = create_app()
    fixed = failed = 0
    candidates = []
    oversold = []
    no_share_flows = 0
    no_flow = 0
    mismatched = 0

    with app.app_context(), get_db() as db:
        query = db.query(Position).filter(
            Position.quantity > 0,
            Position.ownership_status == 'active',
        )
        if args.family is not None:
            query = query.filter(Position.family_id == args.family)
        if args.symbol:
            query = query.filter(Position.symbol.like(f'%{args.symbol.strip()}%'))

        for pos in query.order_by(Position.id).all():
            flow_rows = db.query(Transaction.quantity).filter(Transaction.position_id == pos.id).all()
            if not flow_rows:
                no_flow += 1
                continue
            if not any((q or 0) != 0 for (q,) in flow_rows):
                no_share_flows += 1  # 只有金额流水（货币基金）：派生份额恒 0，不是卖完
                continue
            expected, _ = compute_anchored_state(db, pos)
            if expected > 0:
                if expected != pos.quantity:
                    mismatched += 1
                continue
            if expected < 0:
                # 超卖（卖出多于买入）是**另一种病**：多半是买入腿缺失，真实持仓可能 > 0。
                # 批量清仓会把真实持仓抹掉，故一律不动、只报数交人工核对。
                oversold.append((pos.id, pos.symbol, pos.quantity, expected))
                continue
            candidates.append((pos.id, pos.family_id, pos.ledger_id, pos.symbol, pos.name, pos.quantity, expected))

        print(f'候选 {len(candidates)} 条（应有份额恰好为 0 且仍有份额）')
        print(f'跳过：无任何流水 {no_flow} 条；只有金额流水 {no_share_flows} 条')
        print(f'另有 {mismatched} 条「份额 ≠ 派生值但 > 0」不在本脚本范围')
        print(f'另有 {len(oversold)} 条超卖（派生值为负，疑似缺买入腿），需人工核对、本脚本不动\n')
        for pid, symbol, cur_units, exp_units in oversold[:5]:
            print(
                f'  ! 超卖 #{pid} {symbol} 份额 {Money.min_unit_to_shares(cur_units):g} '
                f'vs 派生 {Money.min_unit_to_shares(exp_units):g}'
            )
        if len(oversold) > 5:
            print(f'  …超卖另有 {len(oversold) - 5} 条')
        if oversold:
            print()

        for pid, family_id, ledger_id, symbol, name, cur_units, exp_units in candidates[: args.limit]:
            print(
                f'  #{pid} {symbol} {(name or "")[:14]} ledger={ledger_id} '
                f'份额 {Money.min_unit_to_shares(cur_units):g} → 应 {Money.min_unit_to_shares(exp_units):g}'
            )
        if len(candidates) > args.limit:
            print(f'  …另有 {len(candidates) - args.limit} 条（--limit 调大看全）')

        if not args.apply:
            print('\nDRY-RUN：未写库。确认无误后加 --apply。')
            return 0
        if not candidates:
            return 0

        backup = _backup(app_database_url())
        print(f'\n备份: {backup}' if backup else '\n备份: 跳过（非 sqlite 文件库，请自行确认回滚方式）')

        for pid, family_id, *_ in candidates:
            try:
                # allow_clear：本脚本的唯一目的就是清掉「流水齐平、份额是重建假象」的
                # 幽灵持仓（--apply 前已逐条列给用户确认）。UI 入口一律不带这个开关，
                # 因为那里的「流水算到 0」不缺证据、缺的是账单（见 position_recompute_entry）。
                data = recompute_with_audit(db, family_id, pid, reason=_REASON, allow_clear=True)
                db.commit()
                fixed += 1
                print(
                    f'  ✓ #{pid} {data["symbol"]} {data["quantity_before"]:g} → '
                    f'{data["quantity_after"]:g}（{data["ownership_status_after"]}，log {data["log_id"]}）'
                )
            except Exception as e:  # noqa: BLE001  单条失败不中断整批，最后汇总
                db.rollback()
                failed += 1
                print(f'  ✗ #{pid} 失败：{e}')

    print(f'\n完成：修正 {fixed} 条，失败 {failed} 条')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

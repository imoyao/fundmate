# -*- coding: utf-8 -*-
"""重建投顾「推导类」调仓历史（#1622 一次性数据修复，幂等；默认 dry-run）。

背景
----
修复前 `AdvisorPortfolioSyncJob._derive_adjust_from_snapshots` 把**净值漂移**也记成调仓
（逐日写入、还带 `op=5 持平` 行，见 #1622），库里因此堆了大量噪音：自选页的「调仓历史」
每个交易日都有一条。修复后判据改成「`|Δratio| > 0.5pp` 的真实变化」，本脚本把历史里的
**推导类**记录按新算法重建：

1. 删除 reason 含「持仓快照推导」的行（= 我们自己推导出来的那些）；
2. 用该组合现存的持仓快照序列逐日重推——**调用与线上同一套逻辑**，避免两份实现漂移。

安全边界
--------
- **官方调仓行绝不触碰**：天天基金等平台的官方调仓行 reason 由平台给出（不含「持仓快照推导」），
  本脚本只删/重建推导类行；
- **不改持仓快照**（`advisor_holdings` 是事实来源，只读）；
- 幂等：重复执行结果一致；默认 dry-run，`--apply` 才落盘。

用法（在 backend/ 目录下）
    pdm run python scripts/repair_advisor_adjust_history.py                  # dry-run 全量
    pdm run python scripts/repair_advisor_adjust_history.py --code ZH012926  # 只看一个组合
    pdm run python scripts/repair_advisor_adjust_history.py --apply          # 落盘
"""

import argparse
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.core.database import market_session  # noqa: E402
from app.domains.funds.models import AdvisorAdjustHistory, AdvisorHolding, AdvisorPortfolio  # noqa: E402
from app.services.sync.jobs.advisor_portfolio_job import AdvisorPortfolioSyncJob  # noqa: E402

#: 推导类行的 reason 特征（与 job 里的文案保持一致；官方调仓行不含此串）
DERIVED_REASON_MARK = '持仓快照推导'


def _portfolio_ids_with_derived(db) -> list[int]:
    rows = (
        db.query(AdvisorAdjustHistory.portfolio_id)
        .filter(AdvisorAdjustHistory.reason.like(f'%{DERIVED_REASON_MARK}%'))
        .distinct()
        .all()
    )
    return sorted({r[0] for r in rows})


def main() -> int:
    parser = argparse.ArgumentParser(description='重建投顾推导类调仓历史（#1622）')
    parser.add_argument('--apply', action='store_true', help='真正落盘（默认只打印）')
    parser.add_argument('--code', default=None, help='只处理指定组合代码')
    args = parser.parse_args()

    with market_session() as db:
        if args.code:
            portfolio_ids = [p.id for p in db.query(AdvisorPortfolio).filter(AdvisorPortfolio.code == args.code).all()]
            if not portfolio_ids:
                print(f'未找到组合 {args.code}')
                return 2
        else:
            portfolio_ids = _portfolio_ids_with_derived(db)

        print(f'待处理组合 {len(portfolio_ids)} 个（{"落盘" if args.apply else "dry-run"}）')
        job = AdvisorPortfolioSyncJob(db=db)
        total_deleted = total_rebuilt = 0
        for pid in portfolio_ids:
            p = db.query(AdvisorPortfolio).filter(AdvisorPortfolio.id == pid).one()
            dates = [
                d
                for (d,) in db.query(AdvisorHolding.as_of_date)
                .filter(AdvisorHolding.portfolio_id == pid)
                .distinct()
                .order_by(AdvisorHolding.as_of_date)
                .all()
            ]
            deleted = (
                db.query(AdvisorAdjustHistory)
                .filter(
                    AdvisorAdjustHistory.portfolio_id == pid,
                    AdvisorAdjustHistory.reason.like(f'%{DERIVED_REASON_MARK}%'),
                )
                .delete(synchronize_session=False)
            )
            rebuilt = 0
            source = (p.platform or 'QIEMAN').lower()
            for day in dates:
                # 刻意复用 job 的内部方法：与线上同一套推导逻辑，避免两份实现漂移（同仓内部脚本）
                rebuilt += job._derive_adjust_from_snapshots(p, day, source)  # noqa: SLF001
            official = (
                db.query(AdvisorAdjustHistory)
                .filter(
                    AdvisorAdjustHistory.portfolio_id == pid,
                    ~AdvisorAdjustHistory.reason.like(f'%{DERIVED_REASON_MARK}%'),
                )
                .count()
            )
            total_deleted += deleted
            total_rebuilt += rebuilt
            print(
                f'  {p.code:<12} {p.name or "":<18} 快照 {len(dates):>3} 天 | '
                f'删除推导行 {deleted:>5} → 重建 {rebuilt:>4} 行 | 官方行保留 {official:>4}'
            )
            if args.apply:
                db.commit()
            else:
                db.rollback()

        print(
            f'合计：删除推导行 {total_deleted} 行 → 重建 {total_rebuilt} 行'
            + ('' if args.apply else '（dry-run，未落盘；加 --apply 生效）')
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())

# -*- coding: utf-8 -*-
"""回填货基七日年化收益率 `money_fund_daily_worth.annual_return_7d`（#2120 P0-1）。

背景
----
该列自建表起就存在（注释写着「七日年化收益率(%)，精度0.0001」），但写入侧
`FundNavSyncJob._save_data` 一直写死 `None  # 暂不计算`，`async_backfill` 干脆
不写这个键——于是 **121 万行、填充率 0.00%**（实测 2026-10-13）。而详情页
`fund_performance._money_fund_performance` 读的正是它，导致**货基「七日年化」恒为 `—`**。
本脚本用 `app/services/money_fund_yield.py` 的统一口径把存量补齐。

口径（不在脚本里另写一套，见 `money_fund_yield` 模块 docstring）
--------------------------------------------------------------
    七日年化(%) = [ Σ(该行往前 7 个**自然日**窗口内已发布的万份收益) / n ] / 10000 × 365 × 100
    n < 2 → NULL（不补 0、不补均值）

安全模型
--------
- **默认 dry-run**，只有显式 `--apply` 才写库；
- **幂等**：值相同的行不写，重跑一次 `changed = 0`；
- **不做全库快照**（invest.db 已 1.2GB，而本脚本只改一列派生值）。
  回滚成本极低：被改的行**原本全部是 NULL**，回滚即
  `UPDATE money_fund_daily_worth SET annual_return_7d = NULL;`
  （确需只回滚本次范围时，先跑 dry-run 记下受影响基金清单）。
- 口径计算全部委托 `money_fund_yield.recompute_annual_return_7d`，脚本只负责
  参数、进度与提交——**避免两处各算一套**。

用法
----
  pdm run python scripts/backfill_money_fund_annual_return_7d.py                     # dry-run
  pdm run python scripts/backfill_money_fund_annual_return_7d.py --limit-funds 5      # 抽样演练
  pdm run python scripts/backfill_money_fund_annual_return_7d.py --fund-code 000379    # 单只
  pdm run python scripts/backfill_money_fund_annual_return_7d.py --apply               # 真正写入
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import database  # noqa: E402
from app.services.money_fund_yield import recompute_annual_return_7d  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description='回填货基七日年化收益率（#2120 P0-1）')
    parser.add_argument('--apply', action='store_true', help='真正写库（默认 dry-run，不改任何数据）')
    parser.add_argument('--fund-code', action='append', dest='fund_codes', help='只处理指定基金（可重复）')
    parser.add_argument('--limit-funds', type=int, default=0, help='只处理前 N 只基金（演练用，0=全部）')
    args = parser.parse_args()

    db = database.get_session()
    try:
        codes = args.fund_codes
        if args.limit_funds and not codes:
            from app.domains.funds.models import MoneyFundDailyWorth

            codes = [
                row[0]
                for row in db.query(MoneyFundDailyWorth.fund_code)
                .distinct()
                .order_by(MoneyFundDailyWorth.fund_code)
                .limit(args.limit_funds)
                .all()
            ]
            print(f'[scope] 抽样 {len(codes)} 只基金（--limit-funds {args.limit_funds}）')

        stats = recompute_annual_return_7d(db, fund_codes=codes, apply=args.apply)

        # 写库后统计填充率，供人工确认效果
        if args.apply:
            db.commit()
            from app.domains.funds.models import MoneyFundDailyWorth

            total = db.query(MoneyFundDailyWorth).count()
            filled = db.query(MoneyFundDailyWorth).filter(MoneyFundDailyWorth.annual_return_7d.isnot(None)).count()
            stats['fill_rate'] = f'{100.0 * filled / total:.2f}%' if total else 'n/a'
            stats['filled_rows'] = filled
            stats['total_rows'] = total

        mode = 'APPLY' if args.apply else 'DRY-RUN'
        print(f'[{mode}] 基金 {stats["funds"]} 只 / 扫描 {stats["scanned"]} 行 / 变动 {stats["changed"]} 行')
        for key in ('total_rows', 'filled_rows', 'fill_rate'):
            if key in stats:
                print(f'[{mode}] {key}: {stats[key]}')
        if not args.apply:
            print('[DRY-RUN] 未写任何数据。确认无误后加 --apply 执行。')
        else:
            print('[APPLY] 回滚命令：UPDATE money_fund_daily_worth SET annual_return_7d = NULL;')
    finally:
        db.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

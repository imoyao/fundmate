# -*- coding: utf-8 -*-
# Author : imoyao
"""`pnl_daily_snapshots` 历史回填 CLI（#3109 图表长周期提速）。

## 为什么需要它

`build_daily_pnl_series` 是**懒物化**：请求某区间时，先把物化行拼上，缺哪天从那天
起现算并写回（`pnl_snapshot_store.save_days`）。于是「第一次请求某个长区间」会把
整段历史都算一遍——真库实测（2026-11-14，6 年 / 112 持仓）：

    近2年 14.7s / 近3年 23.5s / 近5年 50.1s / 成立来 76.4s

前端 `src/utils/http/index.ts` 的全局 timeout 是 **10s**，所以「周期可选」在长档上
不是慢一点，而是**点了必超时、曲线永远出不来**；更糟的是超时会把请求与它的
物化写入一起中断，下次点仍然同样慢（永远学不会）。

把这段一次性成本从「用户点击」挪到「一次运维动作」，之后每个档位的请求都走
全命中路径（拼物化行，毫秒级）；每天新增的那几天由懒物化在下次请求时补。
配合 `core/request_memo` 去掉「逐成员重复的家庭级查询」后，真库同条件实测：
近1月 1.8s / 近1年 2.2s / 近5年 4.8s / 成立来 5.2s（回填前为 76.4s）。

## 用法

    pdm run python backend/scripts/backfill_pnl_snapshots.py            # 预览（dry-run，不写）
    pdm run python backend/scripts/backfill_pnl_snapshots.py --apply    # 真正写入
    pdm run python backend/scripts/backfill_pnl_snapshots.py --ledger 26 --apply
    pdm run python backend/scripts/backfill_pnl_snapshots.py --end 2026-11-13   # 定点复算

## 口径与边界

- 起点 = 该账本**最早一笔资金流水的前一天**：`range_rate` 的分母是「区间前一天净资产」，
  物化少这一天，后续以「最早流水日」为起点的请求仍会缺基线；
- 终点 = 今日；新鲜窗（`PRICE_FRESH_DAYS`）内的日期**不会落库**（`save_days` 的 `max_date`
  保证），那几天恒现算，这是设计而非遗漏；
- 幂等：底层是原生 upsert，重复跑只覆盖同一天，不产生重复行；
- 只写 `pnl_daily_snapshots`，不碰持仓 / 流水 / 净值。
"""

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.domains.ledgers.models import Ledger  # noqa: E402
from app.domains.summary.models import PnlDailySnapshot  # noqa: E402
from app.services.pnl_calendar import build_daily_pnl_series  # noqa: E402
from app.services.scope import first_investment_date  # noqa: E402


def _rows_of(db, ledger_id: int) -> int:
    """该账本当前物化行数（回填前后对比用）。"""
    return db.query(func.count(PnlDailySnapshot.id)).filter(PnlDailySnapshot.ledger_id == ledger_id).scalar() or 0


def _target_ledgers(db, family_id: int, wanted: list[int] | None) -> list[Ledger]:
    query = db.query(Ledger).filter(Ledger.family_id == family_id).order_by(Ledger.id)
    if wanted:
        query = query.filter(Ledger.id.in_(wanted))
    return query.all()


def main() -> int:
    parser = argparse.ArgumentParser(description='pnl_daily_snapshots 历史回填（长周期图表提速）')
    parser.add_argument('--apply', action='store_true', help='真正写入；默认仅预览（写完回滚）')
    parser.add_argument('--family', type=int, default=1, help='家庭 id（默认 1）')
    parser.add_argument('--ledger', type=str, default='', help='只回填指定账本，逗号分隔（默认为该家庭全部）')
    parser.add_argument('--end', type=str, default='', help='终点 YYYY-MM-DD（默认今日，上海时区）')
    args = parser.parse_args()

    from app.core.time_utils import today_shanghai

    end = dt.date.fromisoformat(args.end) if args.end else today_shanghai()
    wanted = [int(x) for x in args.ledger.split(',') if x.strip()] or None

    db = SessionLocal()
    try:
        ledgers = _target_ledgers(db, args.family, wanted)
        if not ledgers:
            print(f'没有匹配的账本（family={args.family}, ledger={wanted}）')
            return 1
        mode = 'APPLY' if args.apply else 'DRY-RUN'
        print(f'[{mode}] pnl_daily_snapshots 回填 family={args.family} 终点={end} 账本数={len(ledgers)}')
        total_rows = 0
        for ledger in ledgers:
            first = first_investment_date(db, args.family, ledger_id=ledger.id)
            if not first:
                print(f'  - 账本 {ledger.id} {ledger.name}: 无流水，跳过')
                continue
            start = dt.date.fromisoformat(first) - dt.timedelta(days=1)
            before = _rows_of(db, ledger.id)
            t0 = time.perf_counter()
            payload = build_daily_pnl_series(db, args.family, start.isoformat(), end.isoformat(), ledger_id=ledger.id)
            cost = time.perf_counter() - t0
            days = len(payload.get('days') or [])
            if args.apply:
                db.commit()
                after = _rows_of(db, ledger.id)
                total_rows += after - before
                print(
                    f'  - 账本 {ledger.id} {ledger.name}: {first}~{end} {days} 天 / '
                    f'物化 {before} → {after}（+{after - before}）{cost:.1f}s'
                )
            else:
                db.rollback()
                print(
                    f'  - 账本 {ledger.id} {ledger.name}: {first}~{end} {days} 天 / '
                    f'预计写入 {days} 行（dry-run 已回滚）{cost:.1f}s'
                )
        if args.apply:
            print(f'完成：共写入 {total_rows} 行物化')
        else:
            print('预览完成：未写入。确认耗时正常后加 --apply 执行。')
    finally:
        db.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

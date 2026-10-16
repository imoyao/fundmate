# -*- coding: utf-8 -*-
"""冷集膨胀守卫巡检（#2123 · P2）。默认 dry-run，`--record` 才落库。

## 它防的是什么

`data-strategy.md` §4.3 的范围强制只挡住「误跑全量」（裸 `--full-sync` 无目标池时 CLI
直接拒绝），挡不住「反复小批量灌」：每次给 50 只冷集基金补一次历史，单看合法，累起来
把清理掉的 800 万行逐步灌回来。而数据膨胀不会报错、不会失败、不会有人投诉。

## 监测什么

**冷集在保留窗口之外的行数**（`stale_rows`）——这才是「该清却没清掉」的量。清理执行
到位后它应等于 floor 保护行数（实测 28 行）；P0-2 的按需取会合法地把它提上来，所以
阈值要放得足够宽（默认单次增量 5,000 行，见 `cold_set_guard.DEFAULT_MAX_GROWTH`）。

## 为什么用 sync_logs 当时序

判定「膨胀」需要上一次的数据，而项目已有每跑一次就落一行的审计表（`stats` 存 JSON）。
复用它就不用新表、不用迁移；代价是它不保证按时间严格排序，所以取最近一条而不做时间匹配。

## 退出码

- `0`：未膨胀（或首次巡检，无基线）
- `1`：膨胀（单次增量超阈值）——便于 cron / CI 直接拿退出码告警

## 用法

  pdm run python scripts/check_cold_set_bloat.py                    # dry-run，只读报告
  pdm run python scripts/check_cold_set_bloat.py --record           # 落库（作为下次基线）
  pdm run python scripts/check_cold_set_bloat.py --max-growth 1000  # 自定义阈值
  pdm run python scripts/check_cold_set_bloat.py --keep-days 1095   # 冷集留 3 年的口径
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import database  # noqa: E402
from app.services import cold_set_guard as guard  # noqa: E402

W = 84


def main() -> int:
    p = argparse.ArgumentParser(description='冷集膨胀守卫巡检（#2123 P2）；默认 dry-run')
    p.add_argument('--record', action='store_true', help='把本次结果落进 sync_logs（作为下次基线）')
    p.add_argument(
        '--max-growth',
        type=int,
        default=guard.DEFAULT_MAX_GROWTH,
        help='单次巡检允许的 stale 行增量（默认 %(default)s）',
    )
    p.add_argument(
        '--keep-days', type=int, default=guard.RETENTION_DAYS, help='冷集保留天数，须与清理脚本一致（默认 %(default)s）'
    )
    args = p.parse_args()

    db = database.get_session()
    try:
        report = guard.measure(db, keep_days=args.keep_days)
        last = guard.last_guard_stats(db)
        report.max_growth = args.max_growth
        guard.compare_with_last(report, last)

        print('=' * W)
        print('冷集膨胀守卫 · %s' % ('RECORD（落库）' if args.record else 'DRY-RUN（只读）'))
        print('=' * W)
        print('保留窗口 近 %d 天（cutoff=%s）| 单次增量阈值 %d 行' % (args.keep_days, report.cutoff, report.max_growth))
        print('')
        for t in report.tables:
            print('[%s]' % t.table)
            print('  总量      %9d 行' % t.total_rows)
            print('  冷集      %9d 行 / %d 只' % (t.cold_rows, t.cold_funds))
            print('  过期行    %9d 行（冷集且早于 cutoff，floor 保护行就在这里）' % t.stale_rows)
            print('')
        print('合计过期行 %d' % report.total_stale)
        if report.prev_stale is None:
            print('上次巡检   无记录（首次巡检，只建立基线，不判定膨胀）')
        else:
            print('上次巡检   %d 行' % report.prev_stale)
            print('本次增量   %+d 行' % (report.growth or 0))
            verdict = '膨胀！增量超过阈值' if report.bloated else '正常'
            print('判定       %s' % verdict)
        print('')

        if args.record:
            guard.record(db, report)
            print(
                '已落库 sync_logs（job_name=%s, status=%s）'
                % (guard.GUARD_JOB_NAME, 'bloated' if report.bloated else 'ok')
            )
        else:
            print('DRY-RUN：未落库。加 --record 才会写入基线。')
    finally:
        db.close()

    if report.bloated:
        print('')
        print('!! 冷集过期行单次增量 %d 超过阈值 %d' % (report.growth or 0, report.max_growth))
        print('   可能原因：误跑了批量回填 / 有人反复小批量灌 / 保留窗口口径被改小')
        print('   建议：先用 preview_daily_worth_retention.py 看清是哪些基金，再决定是否重跑清理')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

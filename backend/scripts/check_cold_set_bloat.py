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

⚠️ 但 `cutoff` 是「今天 - 保留天数」，**它会随时间自己往前挪**，把窗口推过老行 ⇒
直接拿两次的绝对值相减，会把「时间流逝」也算成增长（真库实测 30 天 ≈ 7.9 万行漂移，
阈值 5,000 下只要间隔超过两天就必然判膨胀）。故判定前先按**上次的 cutoff** 在今天
的数据上重算一次（`resolve_baseline`），只让「真正新写进来的老行」计入增量；
阈值同时按间隔折算（`growth_limit`），避免「判定取决于跑得多勤」。

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
import math
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import database  # noqa: E402
from app.services import cold_set_guard as guard  # noqa: E402

W = 84
# 阈值的基准周期：`--max-growth` 按 7 天的量理解，实际阈值按间隔天数折算。
WEEKLY_BASIS_DAYS = 7


def resolve_baseline(g_mod, db, last, today_cutoff):
    """按上次巡检的 cutoff 在今天的数据上重算过期行，得到**同口径**的当前值。

    `cutoff = 今天 - keep_days`，所以「回到上次的窗口」= 拿「今天 - 上次 cutoff」天
    当 keep_days 重算一次（`measure` 因此不必新增 cutoff 参数——那里已顶满体量基线）。
    返回 `(同口径过期行, 间隔天数)`；上次记录缺 cutoff / 同一天重跑时过期行为 None。

    注意两个天数不是一回事：**间隔** = 两次 cutoff 之差（keep_days 不变时等于已过天数），
    **重现旧窗口的 keep_days** = 今天 - 上次 cutoff（实测 395，不是 30）——混用会算成
    「近 30 天」的过期行，比真实值大一个数量级。
    """
    if not last or not last.get('cutoff'):
        return None, None
    try:
        prev_cutoff = date.fromisoformat(str(last['cutoff']))
        days = (date.fromisoformat(today_cutoff) - prev_cutoff).days
    except ValueError:
        return None, None
    if days < 1:
        return None, days
    return g_mod.measure(db, keep_days=(date.today() - prev_cutoff).days).total_stale, days


def growth_limit(max_growth, days):
    """把「7 天允许的增量」按实际间隔折算。

    不折算的话，同一份数据「跑得勤就绿、隔得久就红」——判定变成频率的函数，与
    「灌得多快」无关，而后者才是要拦的东西。
    """
    if not days or days <= WEEKLY_BASIS_DAYS:
        return max_growth
    return math.ceil(max_growth * days / WEEKLY_BASIS_DAYS)


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
        comparable, days = resolve_baseline(guard, db, last, report.cutoff)
        report.max_growth = growth_limit(args.max_growth, days)
        guard.compare_with_last(report, last, comparable)

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
        if comparable is not None:
            print(
                '同口径重算 %d 行（按上次 cutoff=%s 统计，间隔 %d 天；折算阈值 %d 行）'
                % (comparable, last['cutoff'], days, report.max_growth)
            )
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

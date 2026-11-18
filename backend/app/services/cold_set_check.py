# -*- coding: utf-8 -*-
"""冷集膨胀巡检的**执行流程**（#3078）：测量 → 同口径重算 → 阈值折算 → 判定 → 落库。

## 为什么单独成模块

`cold_set_guard` 只管口径与测量（`measure` / `compare_with_last` / `record`），且已顶满
体量基线（240 行 / max_func 52 / max_cc 8），再加流程必超。而流程必须**只有一份**：
CLI（`scripts/check_cold_set_bloat.py`）与调度器（`local_checks`）各写一遍的话，两处漂移
的表现是「同一份库两次判定不同」——不报错、不失败、没有日志，只有人肉对照才看得出。

## 两处「一眼看不出错」的时间算术

1. **同口径重算**要用「今天 − 上次 cutoff」当 keep_days（真库实测 395），不是两次 cutoff
   之差（30）——写成 30 会算成「近 30 天」的过期行（实测 591,234），大一个数量级。
2. **阈值按间隔折算**：`max_growth` 是 7 天的量，隔 30 天才跑一次不能拿周阈值去比，
   否则判定取决于「跑得多勤」而不是「灌得多快」。
"""

from dataclasses import dataclass
from datetime import date
from math import ceil
from typing import Any, Dict, Optional

from app.services import cold_set_guard as guard

# 阈值的基准周期：`max_growth` 按 7 天的量理解，实际阈值按间隔天数折算。
WEEKLY_BASIS_DAYS = 7


@dataclass
class CheckOutcome:
    """一次巡检的结果 + 判定所依据的同口径数据。

    后两项单独返回是为了**不重复扫描**：CLI 要把「按上次 cutoff 重算得到多少行、间隔几天」
    打印出来，若为此再调一次 `resolve_baseline` 就是第二次全表 COUNT（真库数十秒）。
    """

    report: guard.GuardReport
    comparable: Optional[int]
    days: Optional[int]
    prev_cutoff: Optional[str] = None


def resolve_baseline(db, last: Optional[Dict[str, Any]], today_cutoff: str):
    """按上次巡检的 cutoff 在今天的数据上重算过期行，得到**同口径**的当前值。

    `cutoff = 今天 − keep_days`，所以「回到上次的窗口」= 拿「今天 − 上次 cutoff」天当
    keep_days 重算一次（`measure` 因此不必新增 cutoff 参数——那里已顶满体量基线）。
    返回 `(同口径过期行, 间隔天数)`；无上次记录 / 缺 cutoff / 同一天重跑时过期行为 None。

    注意两个天数不是一回事：**间隔** = 两次 cutoff 之差（keep_days 不变时等于已过天数），
    **重现旧窗口的 keep_days** = 今天 − 上次 cutoff（实测 395，不是 30）——混用会算成
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
    return guard.measure(db, keep_days=(date.today() - prev_cutoff).days).total_stale, days


def growth_limit(max_growth: int, days: Optional[int]) -> int:
    """把「7 天允许的增量」按实际间隔折算。

    不折算的话，同一份数据「跑得勤就绿、隔得久就红」——判定变成频率的函数，与
    「灌得多快」无关，而后者才是要拦的东西。
    """
    if not days or days <= WEEKLY_BASIS_DAYS:
        return max_growth
    return ceil(max_growth * days / WEEKLY_BASIS_DAYS)


def run_check(
    db,
    max_growth: int = guard.DEFAULT_MAX_GROWTH,
    keep_days: int = guard.RETENTION_DAYS,
) -> CheckOutcome:
    """完整跑一次巡检（**不落库**），返回带 `prev_stale` / `growth` / `bloated` 的结果。"""
    report = guard.measure(db, keep_days=keep_days)
    last = guard.last_guard_stats(db)
    comparable, days = resolve_baseline(db, last, report.cutoff)
    report.max_growth = growth_limit(max_growth, days)
    guard.compare_with_last(report, last, comparable)
    # `prev_cutoff` 随结果带出去：调用方（CLI）若在 `record` 之后再读 `last_guard_stats`，
    # 读回的就是**本次**刚落的那条，展示成「按本次 cutoff 重算」——与判定依据不符。
    return CheckOutcome(
        report=report,
        comparable=comparable,
        days=days,
        prev_cutoff=(last or {}).get('cutoff'),
    )


def run_check_and_record(
    db,
    max_growth: int = guard.DEFAULT_MAX_GROWTH,
    keep_days: int = guard.RETENTION_DAYS,
) -> CheckOutcome:
    """跑一次并把结果落进 `sync_logs`（作为下次巡检的基线）。

    调度器走这条；CLI 的 `--record` 也走这条——「调度器跑的那次」与「人手动跑的这次」
    必须落在同一张表、同一种 stats 格式里，否则基线会互相读不回来。
    """
    outcome = run_check(db, max_growth=max_growth, keep_days=keep_days)
    guard.record(db, outcome.report)
    return outcome

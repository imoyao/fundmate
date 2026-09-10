# -*- coding: utf-8 -*-
"""基金指标计算（#1285 消费侧「最大回撤」，口径见设计 §3.10）。

只做**纯计算**：输入净值序列，输出最大回撤与口径元数据；取数（窗口、数据源）由调用方
（自选 enrich）决定，便于同一算法服务不同窗口（近1年/近3年/任期）。

口径说明（§3.10 要求「存口径元数据，不只存数字」）：
- 本模块基于**日频**序列计算，返回 peak/trough 日期与样本量，调用方据此拼 `basis/window`；
- 输入序列口径由调用方保证（当前自选链路用 `daily_worth.acc_nav` 累计净值，即
  「分红不再投」口径的近似复权序列，非严格分红再投复权净值）——该差异必须在下发的
  口径元数据里对用户可见，不能只给一个数字。
"""

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Sequence, Tuple


@dataclass
class MaxDrawdownResult:
    """最大回撤计算结果（含口径所需的过程信息）。"""

    max_drawdown: float  # 负数百分比，如 -18.52
    peak_date: date  # 高点日期
    trough_date: date  # 低点日期
    sample_size: int  # 参与计算的净值点数
    as_of: date  # 序列最后一个净值日（口径透明：用户需知道"截至哪天"）


def compute_max_drawdown(
    points: Sequence[Tuple[date, Optional[float]]],
) -> Optional[MaxDrawdownResult]:
    """计算最大回撤（经典 peak-to-trough 定义）。

    Args:
        points: 按日期升序的 (日期, 净值) 序列；净值 None/<=0 的点被跳过。

    Returns:
        无可算区间（点数不足或全为无效值）时返回 None；否则返回含峰谷日期的结果。

    实现要点：单次遍历维护 running peak。**净值创新高时重置 peak**——这是与「区间首日
    为基准」的常见错误写法的关键差异（后者会漏掉区间中段起算的更深回撤）。
    """
    valid = [(d, float(v)) for d, v in points if v is not None and float(v) > 0]
    if len(valid) < 2:
        return None

    peak_date, peak_nav = valid[0]
    worst = 0.0
    worst_peak: Optional[date] = None
    worst_trough: Optional[date] = None

    for d, nav in valid:
        if nav > peak_nav:
            peak_nav, peak_date = nav, d
            continue
        drawdown = (nav - peak_nav) / peak_nav * 100.0
        if drawdown < worst:
            worst = drawdown
            worst_peak, worst_trough = peak_date, d

    if worst_peak is None or worst_trough is None:
        # 全程单调不回头：无回撤，返回 0 并给出样本量（调用方决定是否展示）
        return MaxDrawdownResult(
            max_drawdown=0.0,
            peak_date=valid[0][0],
            trough_date=valid[-1][0],
            sample_size=len(valid),
            as_of=valid[-1][0],
        )

    return MaxDrawdownResult(
        max_drawdown=worst,
        peak_date=worst_peak,
        trough_date=worst_trough,
        sample_size=len(valid),
        as_of=valid[-1][0],
    )


def load_nav_points(rows: Sequence) -> List[Tuple[date, Optional[float]]]:
    """把 DailyWorth 行（或任何有 date/acc_nav 属性的对象）转成计算用序列。

    优先取累计净值 `acc_nav`；缺失时回退单位净值 `unit_nav`（分红少的短债/货基差异小）。
    """
    out: List[Tuple[date, Optional[float]]] = []
    for r in rows:
        nav = getattr(r, 'acc_nav', None)
        if nav is None:
            nav = getattr(r, 'unit_nav', None)
        out.append((r.date, nav))
    return out

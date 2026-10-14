# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/11
# File : index_percentile.py
# app/services/index_percentile.py
"""指数估值历史分位计算（#1407 拍板「组合方案」，#2028 消费）。

分位不是落库字段，而是**读路径现算**：基线序列存 ``index_valuation_baselines``
（乐咕月频，近 5 年），当前值按窗口内序列实时算百分位。这样窗口是参数而不是
「导数时就定死的口径」——用户想看近 3 年不必重新导数。

方向参数是硬约束（#1407 拍板第 4 条）：PE / PB **越高越贵**（正向，``asc``——
当前值越大、分位越高），股息率**越高越便宜**（反向，``desc``）。不区分方向会把
「高股息率」显示成「高估」，与 #1436「收益率上行 = 债券价格下跌」同属结论翻反
类事故，故方向由调用方**显式传入**、不给默认值兜底，并由单测双向锁定。
"""

from __future__ import annotations

import datetime as dt
from typing import List, Optional

# 分位窗口：近 5 年（#1407 拍板：21 年前后市场结构不可比，过长窗口反而失真）。
# 用 366 闰年修正的天数而非日期运算，避免跨闰年少算一个月的基线点。
PERCENTILE_WINDOW_DAYS = 5 * 366

# 少于该点数不给分位：月频基线 1 年 ≈ 12 点，低于一年的「分位」没有统计意义，
# 前端应显示「—」而不是一个小样本冒充的百分数。
MIN_BASELINE_POINTS = 12

# 方向：asc = 越大越贵（PE / PB）；desc = 越大越便宜（股息率）。
DIRECTION_ASC = 'asc'
DIRECTION_DESC = 'desc'
_VALID_DIRECTIONS = (DIRECTION_ASC, DIRECTION_DESC)


def compute_percentile(
    current: float,
    series: List[float],
    direction: str,
) -> Optional[float]:
    """当前值在历史序列中的百分位（0~100，保留 1 位小数）。

    Args:
        current: 当前值（如最新滚动 PE）。
        series: 历史序列（**不含** current 也可、含也可——含时 current 自身参与
            比较，对月频数十点的序列影响 ≤1 个百分点，可接受）。
        direction: ``asc``（越大越贵，PE / PB）或 ``desc``（越大越便宜，股息率）。
            **无默认值**——方向选错即结论翻反，必须由调用方显式声明。

    Returns:
        0~100 的百分位；序列为空返回 ``None``（调用方降级「—」）。

    口径：``asc`` 下分位 = 序列中严格小于 current 的占比（并列值记半个）；
    ``desc`` 对称（严格大于 current 的占比）。并列记半避免「全是同一个值」的
    死序列给出 0 或 100 的极端误导。
    """
    if direction not in _VALID_DIRECTIONS:
        raise ValueError(f'direction 非法：{direction!r}（仅支持 asc / desc）')

    values = [float(v) for v in series if v is not None]
    if not values:
        return None

    less = sum(1 for v in values if v < current)
    equal = sum(1 for v in values if v == current)
    if direction == DIRECTION_DESC:
        greater = sum(1 for v in values if v > current)
        pct = (greater + 0.5 * equal) / len(values) * 100
    else:
        pct = (less + 0.5 * equal) / len(values) * 100
    return round(pct, 1)


def window_cutoff(today: Optional[dt.date] = None) -> dt.date:
    """分位窗口的起始日期（含）。"""
    today = today or dt.date.today()
    return today - dt.timedelta(days=PERCENTILE_WINDOW_DAYS)

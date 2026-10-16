# -*- coding: utf-8 -*-
"""策略指标层（#2224）——纯函数，零依赖，100% 可单测。

边界
    - 只吃 `list[float]` / `Sequence[float]`，不认识数据库；
    - NaN / None 一律**不伪造**：长度不足返回 None，由策略侧决定降级成 WATCH。
      历史上「用 0 兜底」会让信号在缺失数据上表现得像真的有信号，属静默失真。
"""

from __future__ import annotations

from typing import Sequence


def pct_change(values: Sequence[float]) -> list[float]:
    """逐日涨跌幅（%）。首点无前值 → 0.0（不是 None，因长度对齐更实用）。"""
    out = [0.0]
    for i in range(1, len(values)):
        prev = values[i - 1]
        out.append(0.0 if prev == 0 else (values[i] - prev) / prev * 100.0)
    return out


def annualized_volatility(values: Sequence[float], periods_per_year: int = 252) -> float | None:
    """年化波动率（%）。样本 < 2 返回 None。"""
    if len(values) < 2:
        return None
    rets = pct_change(values)[1:]
    if not rets:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return (var**0.5) * (periods_per_year**0.5)


def max_drawdown(values: Sequence[float]) -> float | None:
    """最大回撤（%，正数表示回撤幅度）。样本 < 2 返回 None。"""
    if len(values) < 2:
        return None
    peak = values[0]
    worst = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100.0
            if dd > worst:
                worst = dd
    return worst


def percentile_rank(values: Sequence[float], window: int) -> float | None:
    """当前值在最近 `window` 个样本中的百分位（0~100）。

    对标参考产品的「净值波动 < 1 买入 / > 75 卖出」——那是**百分位**阈值而非绝对涨跌幅，
    这样规则对高波动与低波动品种都成立，无需逐品种调参。
    样本不足 `window` 时按实际样本计算（并如实反映，不补零）。
    """
    if not values:
        return None
    sample = list(values[-window:]) if window > 0 else list(values)
    if not sample:
        return None
    current = sample[-1]
    below = sum(1 for v in sample if v < current)
    equal = sum(1 for v in sample if v == current)
    # 用 (below + equal/2) 处理并列值，避免序列全平时百分位跳到 0 或 100
    return (below + equal / 2) / len(sample) * 100.0


def cumulative_return(values: Sequence[float]) -> float | None:
    """区间累计收益率（%）。样本 < 2 返回 None。"""
    if len(values) < 2 or values[0] == 0:
        return None
    return (values[-1] - values[0]) / values[0] * 100.0

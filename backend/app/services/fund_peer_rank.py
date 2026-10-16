# -*- coding: utf-8 -*-
"""基金「同类内分位」（#167 · 用户在 #167 认可的口径「同类内排序」）。

## 为什么必须有这一层

风险比**跨类别不可比**：债基年化波动天生 2%、股基 25%，而夏普把波动当风险 ⇒
一个全市场纯夏普榜单会把债基顶到最前面（跌得少嘛）。对「想买股基」的人是误导。

用户对这个问题的表述是「用同一个标准衡量股基/混基/债基的夏普率是不是有问题」——
有问题，但根因不是 rf（常值同减不改排序），是**分母不可比**。

解法不是改公式，是**同类内排序**：债基只跟债基比。绝对值跨类读不通，分位跨类读得通
（「在同类里排前 10%」对任何类别都是同一句话）。

## 分位口径

用**经验分位（empirical CDF）**：`低于当前值的同类样本数 / 同类样本数 × 100`，
与 `market_service._calc_percentile` 同一算法（价格分位那边已用了很久）。理由：
比 min-max 稳健——一个极端值不会把整条标尺压扁。

方向约定：分位**越大越好**。但指标本身的「好」方向不一致（夏普越大越好、最大回撤
越小越好）⇒ 先按 `_LOWER_IS_BETTER` 把「越小越好」的指标取负，再算分位。这样前端只需
记住一句话：「分位越高越好」，不必为每个指标各记一个方向。

## 样本门槛

同类样本 < `MIN_PEER_SAMPLE`（5）时**不出分位**。2 只基金的「同类第一」是噪音
（那等于比大小），出它比不出更坏：用户会当成结论。

## 口径版本

分位依赖 `fund_risk_metrics` 快照，故**只吃 `caliber_version` 与当前一致的行**——
旧口径的行留在库里，若一起进分母，分位会在「两代口径混合」的样本上算出来，
而它看起来完全正常。这是比缺数据更难发现的坑。
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# 同类样本门槛：低于此值不出分位（见模块 docstring）。
MIN_PEER_SAMPLE = 5

# 指标 → 「数值越小越好」吗？算分位前把这一类取负，使**分位越大越好**成为
# 全指标统一的读法（前端只需记一句话，不必为每个指标各记一个方向）。
#
# 回撤类的符号很容易写错，单独说明：库内 `max_drawdown` / `current_drawdown`
# 存的是**负数**（-30 比 -10 更深、更差），所以「-8 优于 -25」= 数值越大越好，
# **不取负**。而 `annual_volatility` 是正数、越小越好 ⇒ 取负。
_LOWER_IS_BETTER: Dict[str, bool] = {
    'sharpe': False,
    'sortino': False,
    'calmar': False,
    'upi': False,
    'return_drawdown_ratio': False,
    'win_rate': False,
    'max_drawdown': False,  # 负数值：越大越浅
    'current_drawdown': False,  # 同上
    'annual_volatility': True,  # 正数值：越小越好
}


def percentile_rank(samples: Sequence[float], value: Optional[float]) -> Optional[float]:
    """经验分位（0~100）：`value` 在 `samples` 中低于它的比例 × 100。

    用 `< value` 而非 `<= value`：与 `market_service._calc_percentile` 一致，
    这样「全样本同值」时分位是 0 而不是 100——0 更保守（不宣称「比所有人都好」）。
    """
    if value is None or len(samples) < MIN_PEER_SAMPLE:
        return None
    below = sum(1 for x in samples if x < value)
    return round(below / len(samples) * 100, 1)


def peer_percentiles(
    rows: Iterable[Tuple[str, int, Dict[str, Optional[float]]]],
    metrics: Sequence[str],
) -> Dict[str, Dict[str, float]]:
    """按 `fund_type_id` 分组，算出每只基金每个指标的同类分位。

    Args:
        rows: 可迭代的 ``(fund_code, fund_type_id, {metric: value})``。
        metrics: 要算分位的指标名列表（须在 `_LOWER_IS_BETTER` 内有定义）。

    Returns:
        ``{fund_code: {metric: percentile}}``；样本不足 / 值缺失 / 类型未知的条目
        **不出现**在结果里（调用方据此降级为「—」，而不是显示一个拿 2 只样本算出的数）。

    只算一次遍历、不落库（L2 派生，D21）。
    """
    # 分组：同 type_id 的样本才是「同类」
    groups: Dict[int, List[Tuple[str, Dict[str, Optional[float]]]]] = {}
    for code, type_id, values in rows:
        if type_id is None:
            continue
        groups.setdefault(int(type_id), []).append((code, values))

    out: Dict[str, Dict[str, float]] = {}
    for _type_id, members in groups.items():
        for metric in metrics:
            if metric not in _LOWER_IS_BETTER:
                continue
            sign = -1.0 if _LOWER_IS_BETTER.get(metric) else 1.0
            scored: List[Tuple[str, Optional[float]]] = []
            for code, values in members:
                v = values.get(metric)
                scored.append((code, None if v is None else sign * float(v)))
            samples = [s for _c, s in scored if s is not None]
            if len(samples) < MIN_PEER_SAMPLE:
                continue  # 同类样本不足：整组该指标都不出分位
            for code, s in scored:
                pct = percentile_rank(samples, s)
                if pct is None:
                    continue
                out.setdefault(code, {})[metric] = pct
    return out


__all__ = ['MIN_PEER_SAMPLE', 'peer_percentiles', 'percentile_rank']

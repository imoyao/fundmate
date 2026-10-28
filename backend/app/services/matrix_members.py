# -*- coding: utf-8 -*-
"""两张矩阵共用的成员截断规则（#2686）。

## WHY 需要一条规则，而不是两张卡各写一个数

重叠度矩阵（#2709）先落地时把上限写成「固定 12 只」，理由是「真实组合 ≤ 8 只」。
2026-10-28 用本地真实库实测后证伪：**排除个股后 140 只基金/ETF/债，top12 只覆盖
49.6% 市值**，top20 才 67%，top30 才 83%。

两条结论：

1. 固定只数与「组合有多分散」无关，分散组合里它会把一半仓位挡在矩阵外，而矩阵
   结论会被当成「整体分散度」来读——这正是 #866 一直在防的错误安心；
2. 相关性矩阵与重叠度矩阵如果各用一套上限，切换视图时行列会不同，用户没法对照。

故收口为**一条按市值覆盖率的规则**，两个矩阵共用：

    target=90% 市值覆盖，最少 8 只（结构要看得见），最多 20 只（可读性硬上限）

为什么上限是 20 而不是 30/50：20×20=400 格，格子 32~36px 约 640~720px，桌面一屏
放得下、格内还写得下 ``0.46`` 这种 4 字符数值；30 列要 1000px+ 且必须横向滚动，
而第 21~30 只每只只占 1~2% 市值，铺成格子读不出任何结论。

未覆盖部分**必须如实下发**（``truncated_count`` / ``truncated_market_value_pct``），
由前端与结论同屏显示——静默截断等于让用户把「已展开部分」的结论当成整体结论。
"""

from __future__ import annotations

from typing import Any, List, Sequence, Tuple

#: 目标市值覆盖率：累计市值达到该比例即可停（先到者胜，不必凑满上限）。
MATRIX_COVERAGE_TARGET = 0.9
#: 成员上限：可读性硬约束（见模块 docstring 的 20×20 论证）。
MATRIX_MAX_MEMBERS = 20
#: 成员下限：低于这个数看不出结构（3 只基金再分散也说明不了组合问题）。
MATRIX_MIN_MEMBERS = 8

#: 百分比换算基数（与 ``holding_overlap._PERCENT_SCALE`` 同值；见该处注释）。
_PERCENT_SCALE = 100


def _market_value(item: Any) -> int:
    """成员市值（分）：负数按 0 处理——脏数据不该把覆盖率算成负数。"""
    value = getattr(item, 'market_value_cents', 0) or 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def select_matrix_members(
    funds: Sequence[Any],
    target: float = MATRIX_COVERAGE_TARGET,
    max_members: int = MATRIX_MAX_MEMBERS,
    min_members: int = MATRIX_MIN_MEMBERS,
) -> Tuple[List[Any], int, float]:
    """按累计市值覆盖挑选矩阵成员。

    Args:
        funds: 成员清单，**必须已按市值降序**（调用方排序；本函数不重排，避免
            与「同市值按 code 稳定」的口径分叉）。
        target: 目标累计市值覆盖率（0~1）。
        max_members: 成员上限。
        min_members: 成员下限（总数足够时才生效）。

    Returns:
        ``(members, truncated_count, truncated_market_value_pct)``：
        - ``members``：参与矩阵的成员（原对象切片，不改元素）；
        - ``truncated_count``：被折叠的只数（0 = 全量展示）；
        - ``truncated_market_value_pct``：被折叠部分占总市值的百分比（保留 1 位）。
          总市值为 0 时为 0.0——此时「未覆盖」没有意义，前端不应据此说「还差 x%」。
    """
    total = len(funds)
    if total == 0:
        return [], 0, 0.0

    limit = max(1, min(total, max(0, max_members)))
    floor = max(0, min(min_members, limit))
    total_mv = sum(_market_value(fund) for fund in funds)

    chosen = limit
    if total_mv > 0:
        cumulative = 0
        for index, fund in enumerate(funds[:limit], start=1):
            cumulative += _market_value(fund)
            if cumulative / total_mv >= target:
                # 先到者胜：够 90% 就停，但不少于下限（结构要看得见）
                chosen = min(limit, max(floor, index))
                break
    else:
        # 市值全为 0（估值缺失）：覆盖率为空谈，按上限取，至少留下限
        chosen = max(floor, min(limit, 1))

    members = list(funds[:chosen])
    truncated = total - chosen
    if truncated <= 0 or total_mv <= 0:
        return members, max(0, truncated), 0.0

    truncated_mv = sum(_market_value(fund) for fund in funds[chosen:])
    pct = round(truncated_mv / total_mv * _PERCENT_SCALE, 1)
    return members, truncated, pct

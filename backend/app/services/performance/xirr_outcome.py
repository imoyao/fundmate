# -*- coding: utf-8 -*-
"""XIRR「不可计算」的显式语义：合理区间、原因码与前置判定。

**为什么要单独一个模块**：`calculate_xirr` 历史上用 `0.0` 同时表示两件完全不同的事——
「收益率确实是 0%」与「算不出来 / 结果不可采信」。前端只能把两者都画成 `0%`，
用户看到的是「我一分没赚」，实际可能是「这个场景根本算不了」。

而这套契约其实早就准备好了，只是实现层没兑现：

- ``frontend/src/composables/useReturnMethod.ts`` 的 ``primaryRate`` 注释写明
  「不把『没算出来』画成 0」，返回 ``null`` 时展示 ``—``；
- ``positionSummaryModel.formatXirr`` 对 ``null`` 返回 ``--``；
- ``backend/app/domains/performance/schemas.py`` 的 ``xirr`` 字段本就是 ``Optional[float]``。

故本模块只做一件事：把「不可计算」变成**显式 None + 可区分的原因码**，
让上层不必再从 ``0.0`` 里猜。合理区间沿用原 ``_safe_return`` 的 ``[-1, 10]``：
年化 −100%（本金全损）到 +1000%，之外视为数据不可信（真库 195 个持仓实测最高
浮盈 2.1 倍，该上限不会误伤真实基金数据）。
"""

from __future__ import annotations

import datetime as dt
import math
from typing import List, Optional, Sequence, Tuple

#: 年化收益率合理区间（开区间）：−100% 到 +1000%
XIRR_MIN_EXCLUSIVE = -1.0
XIRR_MAX_EXCLUSIVE = 10.0

#: 数值噪声阈值：|金额| 或 |收益率| 小于此值按 0 处理（浮点残差，不是真值）
ZERO_EPSILON = 1e-8

#: 不可计算的原因码（随响应返回，前端可据此给不同提示）
REASON_INSUFFICIENT = 'insufficient_cashflows'  # 有效现金流不足 2 笔
REASON_SINGLE_DIRECTION = 'single_direction'  # 现金流同号（全买未卖 / 全卖未买）
REASON_NO_SOLUTION = 'no_solution'  # 求解不收敛，或结果超出合理区间不可采信


def normalize_cashflows(
    cashflows: Optional[Sequence[Tuple[dt.date, float]]],
) -> List[Tuple[dt.date, float]]:
    """过滤数值噪声并统一为 float，保持原顺序（不排序，排序由调用方负责）。"""
    if not cashflows:
        return []
    return [(d, float(a)) for d, a in cashflows if abs(float(a)) > ZERO_EPSILON]


def precheck_reason(cf: Sequence[Tuple[dt.date, float]]) -> Optional[str]:
    """求解前的结构性判定。

    Returns:
        ``None`` 表示「结构上可以求解」（解是否存在由求解器决定）；
        否则返回原因码，调用方应直接按不可计算处理。
    """
    if len(cf) < 2:
        return REASON_INSUFFICIENT
    has_positive = any(a > 0 for _, a in cf)
    has_negative = any(a < 0 for _, a in cf)
    if not (has_positive and has_negative):
        return REASON_SINGLE_DIRECTION
    return None


def is_plausible(value: Optional[float]) -> bool:
    """结果是否落在合理区间内（NaN / inf / 越界一律不可采信）。"""
    if value is None or not math.isfinite(value):
        return False
    return XIRR_MIN_EXCLUSIVE < value < XIRR_MAX_EXCLUSIVE


def normalize_result(value: Optional[float]) -> Optional[float]:
    """把求解结果规范化为「可对外展示的值或 None」。

    - 非有限值 / 超出合理区间 → ``None``（不可采信，**不伪装成 0%**）；
    - 数值噪声（|v| < 1e-8）→ ``0.0``（这是真的 0，不是算不出来）。
    """
    if not is_plausible(value):
        return None
    assert value is not None  # is_plausible 已排除 None，供类型收窄
    return value if abs(value) > ZERO_EPSILON else 0.0


def xirr_fields(cashflows: Optional[Sequence[Tuple[dt.date, float]]], value: Optional[float]) -> dict:
    """组装响应里的 ``xirr`` / ``xirr_reason`` 两字段。

    放在本模块而不是调用方，是为了让「有值 ⇔ 无原因码」这条不变量只有一处实现：
    调用方拿到 ``None`` 就一定是「不可计算」，并总能读到原因。
    """
    reason = None
    if value is None:
        reason = precheck_reason(normalize_cashflows(cashflows)) or REASON_NO_SOLUTION
    return {'xirr': None if value is None else round(value, 4), 'xirr_reason': reason}

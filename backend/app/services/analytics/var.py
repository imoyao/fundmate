# -*- coding: utf-8 -*-
"""风险价值 VaR 与年化波动率（#994 模块二 · 偏离与风险控制）。

**基金级**指标：输入净值/价格序列，输出「95% 置信度下该标的单日最大可能亏损」
（VaR）与年化波动率。与 ``analytics/behavior.py``（账户级）不同，本模块只看标的
自己的历史序列，不碰用户流水——盈米 ``AnalyzeFundRisk`` 的自研替代落点
（#1986 检查单「模块二」行；触发依据见 #994 2026-10-17 Phase 拆分评论：
VaR 95% 置信由本卡自建，不走盈米代理）。

## 口径（改动前先读）

1. **日收益**：``r_i = (p_i − p_{i−1}) / p_{i−1}``，序列按日期升序；非正价格
   （脏行/停牌零值）跳过，不用它污染收益序列。
2. **VaR 95% = 历史模拟法（nearest-rank）**：把窗口内全部日收益升序排，取第
   ``k = ceil(0.05 × n)`` 小（1 起数）作为 95% 分位——「过去一年里最差的 5%
   日子，单日亏多少」。不假设正态分布：基金收益现实分布肥尾，参数法（方差×1.65）
   会系统性低估尾部；历史模拟直接数出来，用户可复核。
3. **年化波动率**：日收益样本标准差（ddof=1）× √252，与
   ``fund_performance._annualized_volatility`` 同一算式同一常数——
   详情页「业绩与风险」卡的 ``volatility_1y`` 与本模块不许有两个数。
4. **最小样本 60 个日收益**（约一季度交易日）：低于此值两项都返回 ``None`` +
   ``insufficient_reason``——5% 分位在 30 个样本下只落在 1.5 个点上，
   是噪音不是风险度量（全仓「诚实降级」纪律，不缩窗口凑数）。
5. **窗口由调用方给**：``since=None`` 表示「序列已是窗口内数据」（pro_risk 经
   ``fetch_product_trend('1Y')`` 取数，365 自然日，与 ``volatility_1y`` 同窗）。
   传日期则按日期再过滤，与 ``_annualized_volatility(points, since)`` 同约定。

## 边界

- 只做纯计算：不查库、不抓数、不落库（D21 按需算）。序列口径（acc_nav /
  adj_close）由调用方决定并随值下发，本模块不判定。
- VaR 是**历史分布的外推**：caveat 明示「假设过去一年的日收益分布重现」——
  分布漂移（换经理/改策略）时失效，用户换窗口要能对上账。
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.fund_risk_metrics import TRADING_DAYS_PER_YEAR

#: 窗口内最少日收益样本（约一季度交易日）。低于此值不出值（诚实降级）。
MIN_RETURNS = 60

#: VaR 置信度（95%，行业惯例；99% 对零售用户过于保守——#994 定稿评论待确认项 5）。
VAR_CONFIDENCE = 0.95

_CAVEATS = [
    'VaR 为历史模拟法：假设过去一年的日收益分布重现，分布漂移时失效',
    '波动率按日收益样本标准差年化（×√252），未做异常值处理',
]


def _clean_points(points: Sequence[Tuple[date, float]], since: Optional[date] = None) -> List[Tuple[date, float]]:
    """剔除非正/非有限价格，按日期升序去重（同日保留后者）。"""
    cleaned: Dict[date, float] = {}
    for d, v in points or []:
        if v is None:
            continue
        fv = float(v)
        if not math.isfinite(fv) or fv <= 0:
            continue  # 非正价格不进序列（脏行/停牌零值会造出假收益）
        if since is not None and d < since:
            continue
        cleaned[d] = fv  # 同日后写覆盖先写（与 DB 唯一约束语义一致）
    return [(d, cleaned[d]) for d in sorted(cleaned)]


def _daily_returns(ordered: Sequence[Tuple[date, float]]) -> List[float]:
    """由已清洗的升序序列算日收益率（``r_i = (p_i − p_{i−1}) / p_{i−1}``）。"""
    return [(ordered[i][1] - ordered[i - 1][1]) / ordered[i - 1][1] for i in range(1, len(ordered))]


def _annualized_volatility(returns: Sequence[float]) -> Optional[float]:
    """年化波动率（%）：样本标准差（ddof=1）× √252。

    与 ``fund_performance._annualized_volatility`` 同算式同常数（那里是私有函数、
    且按「窗口过滤 + 取点」合一封装；本模块只吃已过滤的收益序列，故不复用其实现，
    只对齐口径——两处数字必须相等，由 test_pro_risk 的等价性断言钉住）。
    """
    n = len(returns)
    if n < 2:
        return None
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    return round(math.sqrt(var) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100, 2)


def _historical_var(returns: Sequence[float], confidence: float = VAR_CONFIDENCE) -> Optional[float]:
    """历史模拟法 VaR（%，负数）= 窗口内第 (1−confidence) 分位日收益。

    nearest-rank：``k = ceil((1 − confidence) × n)``，取升序第 k 小（1 起数）。
    不插值——5% 分位附近的样本本就稀疏，插值出来的精度是假的。
    """
    n = len(returns)
    if n < MIN_RETURNS:
        return None
    k = max(1, math.ceil((1.0 - confidence) * n))
    return round(sorted(returns)[k - 1] * 100, 2)


def compute_var_metrics(points: Sequence[Tuple[date, float]], since: Optional[date] = None) -> Dict[str, Any]:
    """由净值/价格序列计算年化波动率 + VaR 95%（纯函数，不碰 db）。

    Args:
        points: ``(日期, 价格/净值)`` 序列；口径（acc_nav / adj_close）由调用方保证。
        since: 窗口起始日（含）；``None`` = 序列整体即窗口（调用方已按 1Y 取数）。

    Returns:
        ``{annual_volatility, var_95, sample_returns, sample_points, as_of,
        insufficient_reason, caveats}``。样本不足时两个指标为 ``None``，
        ``insufficient_reason`` 说明原因——前端据「有 key 但 null」降级「—」。
    """
    ordered = _clean_points(points, since)
    result: Dict[str, Any] = {
        'annual_volatility': None,
        'var_95': None,
        'sample_returns': 0,
        'sample_points': len(ordered),
        'as_of': (ordered[-1][0] if ordered else None),
        'insufficient_reason': None,
        'caveats': list(_CAVEATS),
    }
    if len(ordered) < 2:
        result['insufficient_reason'] = '无有效净值/价格序列'
        return result

    returns = _daily_returns(ordered)
    result['sample_returns'] = len(returns)
    if len(returns) < MIN_RETURNS:
        result['insufficient_reason'] = f'近一年日收益样本不足（{len(returns)} < {MIN_RETURNS}），不出风险指标'
        return result

    result['annual_volatility'] = _annualized_volatility(returns)
    result['var_95'] = _historical_var(returns)
    return result

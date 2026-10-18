# -*- coding: utf-8 -*-
"""持仓间相关性：Pearson 相关系数矩阵（#994 模块三 · 资产配置与相关性）。

**为什么要这块**：回答组合层面的一个具体问题——「看起来分散、实则同涨同跌」。
用户在五六个标的上各押注 20%，如果它们的相关系数都在 0.9 以上，真实风险敞口
等同于满仓一只；任何账面分散都抵消不了。**相关性是组合风险里唯一能由数据直接
回答、且用户能看懂的一层**（协方差矩阵看不懂、波动率看单个标的没意义）。

## 口径（改动前先读）

1. **收益率口径与本包 ``var.py`` 完全一致**——复用其 ``_clean_points`` /
   ``_daily_returns``（简单日收益 ``r_i = (p_i − p_{i−1}) / p_{i−1}``）。
   不许在本模块另写一套收益率算法：否则同一只基金在模块二与模块三会算出两组
   不同的日收益，用户无法对账（全仓「同一指标不许有两个数」纪律）。
2. **配对 = 日收益按日期取交集**：两只标的各自算出 ``date -> return`` 后再 join，
   而不是先对齐价格。停牌、新基金 lack of history、净值发布延迟都会造成日期
   错位——按日期配对只会丢样本，**不会把两只基金错开一天对上假同期收益**。
3. **Pearson 相关系数**：``cov(x,y) / (std(x) × std(y))``，样本标准差 ddof=1。
   不用 Spearman：日收益的单调非线性不显著，Pearson 才是马科维茨意义上的
   「联合变动」，用户认知成本也最低（-1 ~ +1）。
4. **最小重叠样本 ``MIN_OVERLAP = 60``**（与 ``var.MIN_RETURNS`` 同值）：
   低于此值不出数 + reason。30 个样本算出的 0.8 与 -0.8 都在置信区间里打滚，
   给用户看就是噪音（诚实降级：宁可给「—」，不给假精确）。
5. **零方差必须挡**：任一序列收益全为 0（货基/逆回购净值长期不动、或长期停牌）
   ⇒ 分母为 0，Pearson 数学上未定义 ⇒ 返回 ``None`` + reason，**不给 0**——
   相关系数 0 意味「无关」，而真相是「无信息」，两者天差地别。

## 边界

- 只做纯计算：不查库、不抓数（D21 按需算）。序列口径（acc_nav / adj_close）
  由调用方决定并随值下发。
- 相关系数**不是因果**，也不稳定：动态相关会因危机期一起归 1 而失效。caveat 明示。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 同包内复用（analytics 是同一口径family）：收益率序列算法不许有两份实现，
# 模块二算出的日收益与本模块必须是同一组数字。
from app.services.analytics.var import _clean_points, _daily_returns

#: 配对样本下限（约一季度交易日），与 var.MIN_RETURNS 同值同理由。
MIN_OVERLAP = 60

_CAVEATS = [
    '相关系数为历史区间统计值：市场剧烈波动时各类资产相关性会趋同，历史值不代表未来',
    '相关系数非因果，且随窗口漂移——换窗口结论可能不同',
]


def _return_series(points: Sequence[Tuple[Any, float]]) -> Dict[Any, float]:
    """``(日期, 价格)`` 序列 → ``{日期: 日收益率}``（复用 var 的清洗与收益口径）。"""
    ordered = _clean_points(points)
    returns = _daily_returns(ordered)
    # 收益 i 对应 ordered[i] 这一天与前一天的差额，归属「后一天」的日期
    return {ordered[i][0]: returns[i - 1] for i in range(1, len(ordered))}


def _std(values: Sequence[float]) -> Optional[float]:
    """样本标准差（ddof=1）；样本 <2 返回 None。"""
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(var)


def pearson_correlation(
    base_points: Sequence[Tuple[Any, float]],
    peer_points: Sequence[Tuple[Any, float]],
    min_overlap: int = MIN_OVERLAP,
) -> Dict[str, Any]:
    """两只标的日收益的 Pearson 相关系数（日期交集配对）。

    Args:
        base_points: 基准标的 ``(日期, 价格/净值)`` 序列。
        peer_points: 对比标的 ``(日期, 价格/净值)`` 序列。
        min_overlap: 配对样本下限，默认 ``MIN_OVERLAP``。

    Returns:
        ``{correlation, overlap_days, reason}``。出不了值时 ``correlation=None``
        且 ``reason`` 说明原因——前端据「有 key 但 null」降级「—」，不编数字。
    """
    result: Dict[str, Any] = {'correlation': None, 'overlap_days': 0, 'reason': None}
    base_ret = _return_series(base_points)
    peer_ret = _return_series(peer_points)
    if not base_ret or not peer_ret:
        result['reason'] = '缺少有效净值/价格序列'
        return result

    # 日期交集：只对两只都产生了收益的那一天配对（见口径 2）
    common_days = sorted(set(base_ret) & set(peer_ret))
    xs = [base_ret[d] for d in common_days]
    ys = [peer_ret[d] for d in common_days]
    result['overlap_days'] = len(common_days)
    if len(common_days) < min_overlap:
        result['reason'] = f'同期交易日不足（{len(common_days)} < {min_overlap}），不出相关性'
        return result

    sx, sy = _std(xs), _std(ys)
    # 零方差 ⇒ Pearson 分母为 0，数学上未定义（见口径 5），不许返回 0
    if not sx or not sy:
        result['reason'] = '收益率序列无波动（净值长期不变或长期停牌），相关性不适用'
        return result

    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (len(xs) - 1)
    rho = cov / (sx * sy)
    # 浮点误差可能让 |rho| 略超 1（1.0000000002），夹回去再保留 2 位
    result['correlation'] = round(max(-1.0, min(1.0, rho)), 2)
    return result


def correlation_caveats() -> List[str]:
    """给调用方随值下发的口径提示（深拷贝，防调用方误改模块级常量）。"""
    return list(_CAVEATS)

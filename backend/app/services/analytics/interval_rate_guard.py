# -*- coding: utf-8 -*-
# Author : imoyao
"""区间收益率的失真下限守卫（#2134 口径 4 / D104）。

`benchmark_excess.build_scope_excess` 算的是**简单区间收益率**：

    range_rate = 区间盈亏 / 区间前一天净资产 × 100

只有当分母代表「这段时间的资本规模」时，这个比值才叫收益率。分母被入金稀释到
极小时它会被放大到无意义量级——真库实测家庭**全期**窗口（2020-08-29 起）期初
净资产仅 **519.38 元**、区间盈亏 −53054.60 元 ⇒ `range_rate = -10214.99`。
这个数一旦流进 `excess_return` 就变成「跑输 10199 个百分点」的假结论，agent 会
原样说给用户；前端也会画出一条冲出可视范围的线。

## 判据：只设下界，−100%

- **下界**：无杠杆多头口径下，净资产不会为负 ⇒ 亏损不可能超过期初净资产的 100%。
  跨过 −100% 只能是分母问题（期初还没有资产，或区间内大额入金已经主导），
  不是「亏得多」。故 `< -100` 一律降级 `None` + `baseline_not_representative`。
- **不设上界**：+N% 是可能真发生的（长期 10 倍），给上限设闸会把真实暴涨判成脏数据。
  小基数下的正向放大（期初 519 元、赚 5 万 ⇒ +9600%）因此仍会透出——这是已知取舍，
  登记在 D104 的「边界」里，不在本模块偷偷兜。

## 为什么降级要连带超额与曲线

`excess_return = range_rate − 基准区间涨跌幅`：收益侧失真时两栏是两个不可比基期的
数，相减出来的「百分点」不是超额而是噪声。曲线同理——它是同一比分母的逐日展开，
单值不可信时曲线只是把同一个错数画成一条线，而且会破坏「曲线末点 ≡ 卡片单值」的
契约（`_build_cum_series` docstring）。故三者一起降级。

## 为什么在出口打补丁而不是在计算现场判

`benchmark_excess.py` 是 `guard_service_size.py` 的冻结基线文件（只减不增）：在
`build_scope_excess` 里加一个 `if` 会同时抬高最长函数行数与圈复杂度。守卫放在出口
的一次调用里，主函数零增长，判据本身仍是可单测的纯函数。
"""

from typing import Any, Dict, Optional

from loguru import logger

# 失真下限：−100% = 亏光期初净资产，是数学极限（见模块 docstring）
_RATE_FLOOR_PCT = -100.0
BASELINE_NOT_REPRESENTATIVE = 'baseline_not_representative'


def unrepresentative_rate_reason(rate: Optional[float]) -> Optional[str]:
    """`range_rate` 是否已失真到不可当收益率用；失真回原因码，否则 None。"""
    if rate is not None and rate < _RATE_FLOOR_PCT:
        return BASELINE_NOT_REPRESENTATIVE
    return None


def apply_rate_floor(result: Dict[str, Any]) -> Dict[str, Any]:
    """给 `build_scope_excess` 的结果施加失真下限，就地降级并回同一对象。

    - 失真 ⇒ `range_rate=None`、`range_reason=baseline_not_representative`、
      `excess_return=None`、`series=[]`；
    - `range_baseline` / `range_pnl` / `benchmark` 等**事实字段保持原样**，供复核
      「为什么降级」（前端也靠它们解释「起点资产过小」）；
    - 未失真时原样返回，零行为变化。
    """
    reason = unrepresentative_rate_reason(result.get('range_rate'))
    if reason is None:
        return result

    logger.warning(
        '区间收益率失真降级 scope={} 区间={}~{} range_rate={} baseline={} range_pnl={} reason={}',
        result.get('scope'),
        result.get('start_date'),
        result.get('end_date'),
        result.get('range_rate'),
        result.get('range_baseline'),
        result.get('range_pnl'),
        reason,
    )
    result['range_rate'] = None
    result['range_reason'] = reason
    result['excess_return'] = None
    result['series'] = []
    return result

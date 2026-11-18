# -*- coding: utf-8 -*-
"""收益日历的「清仓残值」口径（2026-11-10）。

## 问题

`pnl_calendar` 的水平值是 ``mv − cost + realized − buy_fee``。份额归零那天
`mv` 与 `cost` 同时消失；若该持仓整个退出水平值，`total_pnl_asof` 就从
`已实现 − 买入费` 掉到 0，这段落差被日差分记成**当日亏损**——方向与该笔
已实现完全相反（清仓日 = 反向记一次累计已实现）。

真库账本 26（招商证券）实测：594 笔流水 / 15 个清仓日全中，各年合计互相
抵消，全窗口合计恰好 ¥0.00，而「累计盈亏」＝ realized ¥21,040.38 − 买入费
¥193.83 = **+¥20,846.55**。用户看到的就是「收益日历合计 ¥0.00」与
「累计盈亏 +2 万」并存。

## 口径

份额 ≤ 0 的持仓**不退场**：`mv` / `cost` 归零，保留残值
``residual = realized_asof − buy_fee_asof``。

残值在清仓之后是**常量**，日差分恒为 0 ⇒ 不影响其后的任何一天；只有最后一笔
卖出 / 迟到的分红那天含真实盈亏，那正是当日收益。这条与
`compute_range_attribution` docstring 的承诺一致（已实现含在水平值里，清仓的
品种不会在退出那天凭空消失）——此前代码与那段说明是矛盾的。

连带两条：

- **分红等非份额流水必须进 `txns`**。它们不改变份额，但带着 `realized_pnl`
  （现金分红、兑付差额）；按流水类型挑会把它漏掉，日历合计就永远比「累计
  盈亏」少这一笔（账本 26：29 笔分红合计 ¥573.00）。
- **「账户当日无份额」不等于「今天盈亏 0」**。残值仍在动的那天是真收益，
  判成 `no_position` 就把全账户最后一笔收益从日历里抹掉；残值恒定时差分
  为 0，才落回 `no_position`。这里**不能**报「休市」——那天市场可能正常
  开盘，只是你没有仓位。

## 为什么单独成文件

`scripts/guard_service_size.py` 把 `pnl_calendar.py` 冻结为「只减不增」
（lines / max_func / max_cc 三项都是硬基线），残值与状态判定的代码挤进去必判红。
本文件是**新增**叶子模块，按 `NEW_FILE_LIMITS`（≤800 行 / 单函数 ≤120 /
圈复杂度 ≤20）判；`pnl_calendar` 只留一行调用。

## 依赖方向

叶子：只依赖 models，**不** import `pnl_calendar`（后者 import 本模块）。
状态码由调用方传入，避免反向依赖。
"""

from typing import Optional

from app.domains.positions.models import Position


def residual_level(realized: int, fee_cum: int) -> int:
    """清仓持仓应保留在水平值里的残值（分）。"""
    return realized - fee_cum


class ResidualBook:
    """当日「清仓残值」记账器：把归因 / 分桶的样板从 `_compute_days` 挪出来。

    `_compute_days` 的行数与圈复杂度都是冻结指标，多一个 `if` 都要重取基线，
    故三个可选出口（归因明细 / 大类分桶 / 都不写）全部收在这里。
    """

    __slots__ = ('level', 'attribution', 'by_class', 'bucket_key', 'split')

    def __init__(
        self,
        level: dict,
        attribution: Optional[dict],
        by_class: dict,
        bucket_key,
        split: bool,
    ) -> None:
        self.level = level
        self.attribution = attribution
        self.by_class = by_class
        self.bucket_key = bucket_key
        self.split = split

    def add(self, state: dict, pos: Position) -> int:
        """把该持仓当日的清仓残值记进水平值，返回计入金额（分）。

        调用方无条件 `+=`：残值为 0 时返回 0，不必在外层再判一次。
        """
        residual = residual_level(state['realized'], state['fee_cum'])
        if not residual:
            return 0
        self.level[pos.id] = residual
        if self.attribution is not None:
            # 有贡献就必须进 `priced`：归因行取自这个集合，漏掉会让
            # `Σ 明细 ≠ 合计`（整窗无价的清仓持仓正是这一类）。
            self.attribution['priced'].add(pos.id)
        if self.split:
            bucket = self.bucket_key(pos)
            if bucket is not None:
                self.by_class[bucket] = self.by_class.get(bucket, 0) + residual
        return residual


def cleared_residual_day(day_held_count: int, day_opening: bool, daily_pnl: Optional[int]) -> bool:
    """「账户无份额、但残值这天动了」⇒ 真收益，不能判成 no_position。

    清仓后持仓不再进 `day_held_count`，但这些天仍可能有真实盈亏——最后一笔
    卖出、清仓后到账的分红。判成 `no_position` 就把全账户最后一笔收益从日历里
    抹掉，合计从此对不上「累计盈亏」。残值恒定时差分为 0（`daily_pnl` 0 或
    None），才落回「今天没有仓位」。

    这里**不能**报「休市」：那天市场可能正常开盘，只是你没有仓位——故本判据
    只回答「这天算不算有收益」，状态码由调用方给。
    """
    return day_held_count == 0 and not day_opening and bool(daily_pnl)

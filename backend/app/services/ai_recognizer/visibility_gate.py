# -*- coding: utf-8 -*-
"""可见账户门控：作用域绑死 family 的指标，在「只看得见部分账户」时明说不可用。

## 为什么需要这一层

一部分 agent 工具的**输出语义绑定家庭全量**：

- `build_benchmark_comparison`：区间收益是「全家庭组合」的收益，超额 = 它减基准；
- `compute_range_attribution`：每行 `contribution_pct` 的分母是**区间合计**，
  `Σ items ≡ 区间合计` 由引擎同一次遍历**构造保证**（#2135）；
- `build_rebalance_reference`：偏离度是「全家庭持仓」相对目标配置算的，行业穿透
  走 `build_penetration(db, family_id)`。

它们的引擎只接受 `family` 或**单个** `ledger`，没有「账户集合」这一档
（`build_scope_excess` / `build_daily_pnl_series` / `compute_range_attribution`
的 `ledger_id` 都是 `Optional[int]`）。于是「部分可见」时只剩两条路：

1. **原样返回**：数值里混着用户看不见的账户的钱 —— 与「明细不可见」直接矛盾；
2. **在工具层过滤 items 再重算合计**：等于另起一套算账，`Σ` 的构造保证当场失效
   （过滤掉一个账户的贡献后，合计的分母就不再是引擎算的那个）。

两条都是错的，所以第三条：**不给数，只给口径**。这是 D127「失败方向少看见」的
延伸——「算不准」比「算错」诚实。

## 与「集合型工具」的区别

XIRR / 交易行为 / 自选市值是**集合上可定义的统计**（把可见账户当成一个子组合，
分子分母同口径），所以它们走 `restrict_visible` 过滤后照常出数，**不进门控**。
判据是：输出的定义域是否依赖「家庭全部账户」这个前提。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

from app.domains.ledgers.models import Ledger

#: 门控命中时统一下发的提示。带上「怎么办」，否则模型只会复述「不可用」。
PARTIAL_VISIBILITY_HINT = (
    '当前账号只能看见部分账户。本指标按家庭全量计算，会把你看不见的账户也算进去，'
    '所以不提供这个数。需要它的话，请让账户所有者在账户设置里把可见性改为共享。'
)


def partial_visibility_payload(db: Any, family_id: int, visible_ids: Optional[Set[int]]) -> Optional[Dict[str, Any]]:
    """返回 None 表示「可以算」；返回 dict 表示「部分可见，明说不可用」。

    三态与 `visibility.restrict_visible` 保持同一套语义：

    - `visible_ids is None`：判定不出主体（MCP / 离线直调），不筛 ⇒ 照常算；
    - 可见集合覆盖家庭全部账户：等价于全可见 ⇒ 照常算（普通成员恰好拥有全部账户
      时也会走到这里，不能因为「传了集合」就判成部分可见）；
    - 真子集：不可用。

    空集不是特例：它只是「一个账户都看不见」的真子集，`hidden == 全部`。
    """
    if visible_ids is None:
        return None
    all_ids = {row_id for (row_id,) in db.query(Ledger.id).filter(Ledger.family_id == family_id).all()}
    visible = set(visible_ids) & all_ids
    hidden = all_ids - visible
    if not hidden:
        return None
    return {
        'available': False,
        'unavailable_reason': 'partial_visibility',
        'visible_account_count': len(visible),
        'hidden_account_count': len(hidden),
        'hint': PARTIAL_VISIBILITY_HINT,
    }


__all__ = ['PARTIAL_VISIBILITY_HINT', 'partial_visibility_payload']

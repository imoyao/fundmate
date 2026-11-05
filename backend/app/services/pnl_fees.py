# -*- coding: utf-8 -*-
"""买入侧手续费（费用损耗）在**盈亏口径**上的唯一出口。

WHY
    `pnl_service` 的成本基数 = 成交价 × 份额，**从不含费**；而卖出侧的费早就
    在 `compute_sell_realized_cents` 里扣进了 `realized_pnl`。于是「买入费」既不在
    成本里、也不在已实现里——投入 10,000 元付 5 元佣金时，那 5 元从账面上凭空消失。
    这不是漏记，是**口径缺了一块**：只有卖出边的费用有归属。

两种口径的取舍（本仓选「损耗」）：

    | 口径 | 成本均价 | 总盈亏 | 与交割单对照 |
    |---|---|---|---|
    | 资本化（券商 APP） | 含费 | 含费 | 对不上成交价 |
    | **损耗（本模块）** | **= 成交价** | **扣费** | **逐笔可核** |

代价是「投入 10000、成本 9950，差额是费用」这种观感；补偿是费用作为一个独立数字
可见（`buy_fee_cents`），而不是被藏进均价里——藏进去就再也拆不出来。

为什么不资本化：改成本均价要历史全量重算，且从此成本价与交割单成交价不一致，
用户逐笔核对时说不出差在哪（决策 D82）。

调用方
    - `pnl_service.position_pnl_cents`：单笔持仓的 `total_pnl_cents` 扣 `buy_fee_cents`；
    - `summary_service`：家庭/账户级汇总（`/api/summary/` 的 `buy_fee_cny`）；
    - `pnl_calendar`：逐日归因（费用记在买入当天，见 :func:`fee_delta_cents`）。
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.transactions.models import Transaction

#: **尚未进任何收益口径**的费用所在类型：买入费。
#:
#: 卖出费早就算进 `realized_pnl`（`pnl_service.compute_sell_realized_cents` 的
#: `− fee_cents`），再在这里减一次就是双扣；买入侧则相反——成本基数 = 成交价 × 份额，
#: 费用从未参与，于是「买入花掉的佣金」在总盈亏里凭空消失。
#: 兑付（bond_redeem）的 `amount` 已是到账净额、`fee` 若存在也已含在里面，故不在本表。
FEE_TXN_TYPES = ('buy', 'deposit')


def fee_delta_cents(txn) -> int:
    """该笔交易应计入盈亏的费用（分，**负数**；不该计的费用返回 0）。

    只对 `FEE_TXN_TYPES` 返回 ``-fee``：卖出的费已经落在流水的 `realized_pnl` 上，
    这里再减就是双扣——那会让卖出日的亏损凭空翻倍。

    返回值带负号是刻意的：调用方一律做加法（``realized + fee_delta``），
    不用在每个调用点各判一次方向。
    """
    if getattr(txn, 'txn_type', None) not in FEE_TXN_TYPES:
        return 0
    try:
        return -int(getattr(txn, 'fee', None) or 0)
    except (TypeError, ValueError):
        return 0


def buy_fee_by_position(db: Session, family_id: int, ledger_ids: Optional[List[int]] = None) -> dict[int, int]:
    """按持仓归集的**买入侧**手续费（分，正数）。

    只收 `FEE_TXN_TYPES`：卖出费早已在 `realized_pnl` 里扣过，这里再收就是双扣。
    孤儿流水（`position_id` 为 NULL，例如清仓后持仓行被删）统一归到哨兵键 0，
    与 `pnl_service.realized_pnl_by_position` 同款。

    ``ledger_ids`` 语义同 `pnl_service.realized_pnl_by_position`。
    """
    query = db.query(Transaction.position_id, func.sum(Transaction.fee)).filter(
        Transaction.family_id == family_id,
        Transaction.txn_type.in_(FEE_TXN_TYPES),
    )
    if ledger_ids is not None:
        query = query.filter(Transaction.ledger_id.in_(ledger_ids))
    rows = query.group_by(Transaction.position_id).all()
    return {(pid or 0): int(total or 0) for pid, total in rows if total}


def family_buy_fee_cents(db: Session, family_id: int, ledger_ids: Optional[List[int]] = None) -> int:
    """家庭级**买入侧**手续费合计（分），口径同 :func:`buy_fee_by_position`。

    取家庭级合计而不是 ``Σ buy_fee_by_position``：已清仓持仓的持仓行会被删，其买入费
    挂在孤儿流水上，按持仓求和会漏掉；而 `realized` 那边是含孤儿的（`family_realized_pnl_cents`
    直接扫全流水），两端口径必须对称，否则「总盈亏」会比「已实现 + 未实现」多一个差额
    且没人说得清差在哪。
    """
    query = db.query(func.sum(Transaction.fee)).filter(
        Transaction.family_id == family_id,
        Transaction.txn_type.in_(FEE_TXN_TYPES),
    )
    if ledger_ids is not None:
        query = query.filter(Transaction.ledger_id.in_(ledger_ids))
    return int(query.scalar() or 0)

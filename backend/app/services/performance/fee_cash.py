# -*- coding: utf-8 -*-
"""手续费在**现金流口径**上的唯一出口（XIRR / 资金流动共用）。

WHY
    `transactions.fee`（分）与 `transactions.amount`（元）是两列，而 `amount` 一律是
    **成交额**（买卖均为毛额，与交割单「成交金额」一致）。现金流要的是「账户里真的
    划走 / 到账多少钱」，两者不等：

    - 买入：现金流出 = ``成交额 + 费``；
    - 卖出：现金流入 = ``成交额 − 费``。

    于是 ``total_return = 当前市值 − 净投入`` 天然把费用算进亏损，与
    `pnl_service` 的 ``realized + unrealized − buy_fee`` 是同一个数
    （验证见 `tests/services/performance/test_fee_in_pnl.py` 的自洽用例）。
    只改一边，收益页与流水页就会各报一个数——那是本仓最忌讳的一种错。

为什么 `amount` 不直接改写成含费金额
    成交额必须与交割单对得上（用户会逐笔核）。费用是另一个维度，合成一个数之后
    「这 5 元是什么」就再也拆不出来，所以本模块只做「按类型加 / 减」，不改写入侧。
"""

from __future__ import annotations

from typing import Optional, Tuple

from app.core.money import Money
from app.services.importer.mappings import BusinessType

#: `amount` 是**毛额**、手续费另行记录的现金类型。
#:
#: 只有买卖两边的成交额是毛额（与交割单「成交金额」一致）。其余类型不可套用：
#: - `bond_redeem`：`amount` 取交割单「发生金额」，即**到账净额**，再扣一次 fee 是双计；
#: - `dividend*`：`amount` 是到账分红，同理；
#: - `deposit` / `withdraw`：银行侧通常不单列费用，写了 fee 也视为已含在金额里。
#:
#: 现金残差是「账户还剩多少现金」的推导值，必须按**真实现金流**算：
#: 买入实际划走 `成交额 + 费`、卖出实际到账 `成交额 − 费`，两个方向都是净减。
FEE_SEPARATE_CASH_TYPES = frozenset({BusinessType.BUY.code, BusinessType.SELL.code})


class Cashflows(list):
    """现金流列表 + 该列表**自带的**手续费合计（元）。

    为什么不是出参（`fees_sink`）也不是返回值二元组：
    手续费合计不是独立结果，它是「这一串现金流里含了多少费」的**属性**——挂在这个
    列表上，就不会出现「传了 sink 忘了读」「换了个调用点忘了传」这类只会在页面上
    显形、代码里看不出的错。且它是 `list` 的子类，既有 `for / sum / sort / ==` 全兼容。

    注意 `fees_total` 只统计**进了本列表**的交易：没进现金流的分红/兑付，其费也不计入——
    两条口径必须同 scope，否则「累计手续费」会比实际参与计算的多。
    """

    fees_total: float = 0.0


def fee_yuan(txn) -> float:
    """该笔交易的手续费（元）；缺失 / 非法一律 0，绝不抛错。

    库内单位是「分」（`transactions.fee`），测试桩与历史数据里可能是 None / 字符串，
    统一按分解释。费用算成 0 只会让「累计手续费」偏小，抛错会让整个收益页 500。
    """
    raw = getattr(txn, 'fee', None)
    if not raw:
        return 0.0
    try:
        return Money.cents_to_yuan(int(raw))
    except (TypeError, ValueError):
        return 0.0


def flow_fee_yuan(flow: dict) -> float:
    """从 `cashflow_layers.collect_flows` 的输出里取该笔的费（元）。"""
    try:
        return float(flow.get('fee') or 0.0)
    except (TypeError, ValueError):
        return 0.0


def signed_cash(
    txn_type: Optional[str],
    amount: float,
    fee: float,
    outflow_types,
    inflow_types,
) -> Tuple[Optional[float], float]:
    """把一笔交易换算成「含费的现金流」：返回 ``(带符号金额, 计入的费)``。

    - 现金流出（买入等）：``-(amount + fee)``
    - 现金流入（卖出等）：``+(amount - fee)``
    - 其它类型（分红 / 兑付 / 入金等）：不在两个集合里，返回 ``(None, 0.0)``
      由调用方自行决定怎么记（它们的 `amount` 已是净额，套用本函数会双计）。

    第二个返回值是**本笔真正计入现金流**的费，供调用方累加「累计手续费」——
    口径必须与现金流一致：没进现金流的交易，其费也不该出现在合计里。
    """
    if txn_type in outflow_types:
        return -(amount + fee), fee
    if txn_type in inflow_types:
        return amount - fee, fee
    return None, 0.0

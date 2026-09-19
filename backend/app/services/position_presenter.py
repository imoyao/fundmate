# -*- coding: utf-8 -*-
"""持仓明细的展示层序列化（唯一出口）。

为什么在 services 而不是 `domains/positions/views.py`（#1607 批次 2）：
- 该函数被 **positions 与 ledgers 两个域**的视图共用，此前 `ledgers/views.py` 直接
  `from app.domains.positions.views import enrich_position_dict`——正是决策中明令禁止的
  「跨域引用对方 views」（域视图互引会把 HTTP 层的路由 / 事务 / 鉴权细节卷进另一域的依赖面）；
- 它自身依赖 services 口径（`position_valuation.market_value_cents`）。按
  `core ← domains.{models,schemas} ← services ← domains.{views}` 的方向，
  「多域共用的展示口径」应落 services，两侧视图各自 import 即可。

不变量：字段与数值口径与迁移前**逐字一致**（`PositionOut` + 三个 label + `Money` 单位换算
+ `market_value` / `pnl` 走唯一市值口径），仅模块位置变化。
"""

from app.core.constants import ALLOCATION_LABELS, MARKET_LABELS, TYPE_LABELS
from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.positions.schemas import PositionOut
from app.services.position_valuation import market_value_cents


def enrich_position_dict(p: Position) -> dict:
    """把 `Position` 序列化为接口返回字典（含枚举标签与展示单位换算）。"""
    if not p.market:
        p.market = 'UNKNOWN'
    d = PositionOut.model_validate(p).model_dump()
    d['type_label'] = TYPE_LABELS.get(p.asset_type, p.asset_type)
    d['market_label'] = MARKET_LABELS.get(p.market, p.market)
    d['allocation_label'] = ALLOCATION_LABELS.get(p.allocation, p.allocation or '未分类')
    # 转换内部单位到展示单位
    d['quantity'] = Money.min_unit_to_shares(p.quantity)
    d['avg_price'] = Money.price_units_to_yuan(p.avg_price)
    d['current_price'] = Money.price_units_to_yuan(p.current_price)
    d['market_value_override'] = (
        Money.cents_to_yuan(p.market_value_override) if p.market_value_override is not None else None
    )
    # 市值/盈亏（#1174 收口）：委托唯一口径 position_valuation.market_value_cents。
    # 本币直算——汇率折算仅存在于 summary 聚合口径（total_*_cny）；单条明细与 current_price 保持本币一致。
    d['market_value'] = Money.cents_to_yuan(market_value_cents(p))
    d['pnl'] = (
        Money.cents_to_yuan(Money.multiply_price_quantity(p.current_price - p.avg_price, p.quantity))
        if p.avg_price
        else 0.0
    )
    return d

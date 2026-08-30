# -*- coding: utf-8 -*-
"""按占比批量更新某产品跨账户总价（P1-4 / roadmap P1-4）。

WHY
    投顾组合 / 银行理财往往只有「组合级估值」，没有逐笔净值；同一产品常分散在多个账户。
    用户只需录入一次产品维度总价，系统按各账户当前市值占比自动分摊写入每笔持仓的
    ``market_value_override``——这正是竞品（钱往/有知有行/同花顺）结构性做不到的差异化能力。

口径约束：
- 分母复用唯一市值口径 ``position_valuation.market_value_cents``（#1174 收口），不另开一套；
- 整数分 + ROUND_HALF_UP；尾差归占比最大一笔（与 position_aggregation 的尾差处理一致）；
- 假设分摊标的均为本币（CNY）场景；跨币种 balance 分摊非本期范围。
- 本服务只写 ``market_value_override`` / ``value_override_at``，不建交易流水、
  不动 quantity；调用方（端点）负责 commit。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from app.core.money import Money
from app.domains.positions.models import Position
from app.services.position_valuation import market_value_cents


def allocate_value(
    db,
    family_id: int,
    symbol: str,
    total_value_yuan: float,
    *,
    as_of: Optional[date] = None,
    ledger_id: Optional[int] = None,
) -> dict:
    """按各账户当前市值占比，把产品总价分摊写入每笔持仓的可写市值。

    Args:
        db: 数据库会话（调用方负责 commit）。
        family_id: 家庭 ID。
        symbol: 产品代码。
        total_value_yuan: 产品维度新总价（元）。
        as_of: 市值录入日期，默认今天。
        ledger_id: 限定只分摊到某账户；缺省跨全部活跃账户。

    Returns:
        dict: ``{ symbol, total_value_cents, total_weight_cents, as_of, allocations[] }``
        ``allocations[]``: ``{ position_id, ledger_id, allocated_cents, allocated_yuan, ratio }``

    Raises:
        ValueError: 无活跃持仓 / 分母（各账户市值之和）为 0 无法按比例分摊。
    """
    positions = (
        db.query(Position)
        .filter(
            Position.family_id == family_id,
            Position.symbol == symbol,
            Position.ownership_status == 'active',
        )
        .all()
    )
    if ledger_id is not None:
        positions = [p for p in positions if p.ledger_id == ledger_id]

    if not positions:
        raise ValueError(f'未找到 symbol={symbol} 的活跃持仓，无法分摊总价')

    # 分母：复用唯一市值口径（本币直算，balance 场景均为 CNY）
    weights = [market_value_cents(p) for p in positions]
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError('当前各账户市值均为 0，无法按比例分摊；请先逐账户录入市值或使用其他方式')

    total_cents = int((Decimal(str(total_value_yuan)) * 100).to_integral_value(rounding='ROUND_HALF_UP'))

    # 首轮按占比四舍五入（整数分）
    allocated = [
        int((Decimal(w) * total_cents / total_weight).to_integral_value(rounding='ROUND_HALF_UP')) for w in weights
    ]

    # 尾差（分）归占比最大一笔，保证 Σ(分配) == 总价，杜绝一分钱对不上
    diff = total_cents - sum(allocated)
    if diff != 0:
        max_idx = weights.index(max(weights))
        allocated[max_idx] += diff

    as_of_date = as_of or date.today()
    allocations = []
    for pos, cents in zip(positions, allocated):
        pos.market_value_override = cents
        pos.value_override_at = as_of_date
        allocations.append(
            {
                'position_id': pos.id,
                'ledger_id': pos.ledger_id,
                'allocated_cents': cents,
                'allocated_yuan': Money.cents_to_yuan(cents),
                'ratio': round(cents / total_cents, 6) if total_cents else 0.0,
            }
        )

    db.flush()
    return {
        'symbol': symbol,
        'total_value_cents': total_cents,
        'total_weight_cents': total_weight,
        'as_of': as_of_date.isoformat(),
        'allocations': allocations,
    }

# -*- coding: utf-8 -*-
"""基金持仓跨账本聚合（#1101）。

把家族内所有基金类持仓（场外 fund / 货基 money_fund，ownership_status='active'）
按维度聚合成统一视图，供资产概览「场外基金(含E账户)」卡片与下钻页使用。

市值口径严格复用 summary_service：份额(份) * 当前价(元) * 汇率，结果以「分」整数汇总，
避免浮点累积误差（与全局资产计算一致）。
"""

from __future__ import annotations

from decimal import Decimal

from app.core.constants import EXCHANGE_RATES
from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position

# 场外基金口径：E账户仅覆盖场外份额，故聚合不含 ETF/LOF 等场内品种
FUND_ASSET_TYPES = ('fund', 'money_fund')


def _position_market_value_cents(position: Position) -> int:
    """单笔持仓市值（分），复用 summary_service 口径。"""
    rate = EXCHANGE_RATES.get(position.currency, 1.0)
    yuan = Money.min_unit_to_shares(position.quantity) * Money.price_units_to_yuan(position.current_price) * rate
    return int((Decimal(str(yuan)) * 100).to_integral_value(rounding='ROUND_HALF_UP'))


def get_fund_aggregation(session, family_id: int, dimension: str = 'product') -> dict:
    """聚合家族基金持仓。

    dimension:
      - 'product'（默认）：按基金代码聚合，每条含来源账本列表（sources）
      - 'institution'：按销售机构（ledger.sales_institution_id）聚合
      - 'app'：按交易前端（ledger.frontend_app）聚合
    """
    positions = (
        session.query(Position)
        .filter(
            Position.family_id == family_id,
            Position.asset_type.in_(FUND_ASSET_TYPES),
            Position.ownership_status == 'active',
        )
        .all()
    )

    ledger_ids = {p.ledger_id for p in positions if p.ledger_id}
    ledgers = (
        {led.id: led for led in session.query(Ledger).filter(Ledger.id.in_(ledger_ids)).all()} if ledger_ids else {}
    )

    rows = []
    for p in positions:
        ledger = ledgers.get(p.ledger_id)
        rows.append(
            {
                'symbol': p.symbol,
                'name': p.name,
                'ledger_id': p.ledger_id,
                'ledger_name': ledger.name if ledger else None,
                'institution_id': ledger.sales_institution_id if ledger else None,
                'frontend_app': ledger.frontend_app if ledger else None,
                'market_value_cents': _position_market_value_cents(p),
                'quantity': p.quantity,
            }
        )

    if dimension == 'institution':
        grouped: dict = {}
        for r in rows:
            key = r['institution_id'] or 'unknown'
            g = grouped.setdefault(key, {'key': key, 'market_value_cents': 0, 'items': []})
            g['market_value_cents'] += r['market_value_cents']
            g['items'].append(r)
        groups = list(grouped.values())
    elif dimension == 'app':
        grouped = {}
        for r in rows:
            key = r['frontend_app'] or 'self'
            g = grouped.setdefault(key, {'key': key, 'market_value_cents': 0, 'items': []})
            g['market_value_cents'] += r['market_value_cents']
            g['items'].append(r)
        groups = list(grouped.values())
    else:  # product
        grouped = {}
        for r in rows:
            g = grouped.setdefault(
                r['symbol'],
                {
                    'symbol': r['symbol'],
                    'name': r['name'],
                    'market_value_cents': 0,
                    'quantity': 0,
                    'sources': [],
                },
            )
            g['market_value_cents'] += r['market_value_cents']
            g['quantity'] += r['quantity']
            g['sources'].append(
                {
                    'ledger_id': r['ledger_id'],
                    'ledger_name': r['ledger_name'],
                    'market_value_cents': r['market_value_cents'],
                    'quantity': r['quantity'],
                }
            )
        groups = list(grouped.values())

    total_mv = sum(g['market_value_cents'] for g in groups)
    return {'total_market_value_cents': total_mv, 'dimension': dimension, 'groups': groups}

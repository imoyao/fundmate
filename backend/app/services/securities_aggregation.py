# -*- coding: utf-8 -*-
"""场内证券（股票/ETF/可转债）持仓跨账本聚合（#1132）。

把家族内全部场内证券持仓（asset_type ∈ {etf, bond, stock}，ownership_status='active'）
按维度聚合成统一视图，供资产概览「场内证券（股票/ETF/可转债）」卡片与下钻页使用。

本服务是 #1101 场外基金聚合（fund_aggregation）的互补集：完全复用其 position 级聚合范式，
不新建虚拟账本、不加列（零 schema 迁移）。设计见
docs/working-notes/securities-aggregation-design-2026-08-29.md（D1~D4 已确认）。

市值口径严格复用 fund_aggregation 的 `_position_market_value_cents`：份额(份) * 当前价(元) * 汇率，
结果以「分」整数汇总，避免浮点累积误差（与全局资产计算一致）。
"""

from __future__ import annotations

from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.services.fund_aggregation import _position_market_value_cents

# #1132 场内证券聚合：单笔市值口径与 #1101 完全一致，直接复用 fund_aggregation 的实现，
# 避免两份逻辑漂移（shares×price×rate → 整数分，禁止浮点直接累积）。
# #1132 范围（D1 已确认）：股票 + ETF + 可转债，即全部场内证券。
SECURITIES_ASSET_TYPES = ('etf', 'bond', 'stock')


def get_securities_aggregation(session, family_id: int, dimension: str = 'product') -> dict:
    """聚合家族场内证券持仓。

    dimension:
      - 'product'（默认）：按 symbol 聚合，每条含来源账本列表（sources）
      - 'institution'：按销售机构（ledger.sales_institution_id）聚合
      - 'app'：按交易前端（ledger.frontend_app）聚合

    与 fund_aggregation 返回结构一致：{total_market_value_cents, dimension, groups[]}。
    """
    positions = (
        session.query(Position)
        .filter(
            Position.family_id == family_id,
            Position.asset_type.in_(SECURITIES_ASSET_TYPES),
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

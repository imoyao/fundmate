# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/7 21:52
# File : views.py
# backend/app/api/views.py
# -*- coding: utf-8 -*-
"""首页仪表盘聚合数据 API."""

from apiflask import APIBlueprint
from flask import jsonify  # 新增

from app.core.database import get_db
from app.domains.assets.models import Asset
from app.domains.positions.models import Position

bp = APIBlueprint('summary', __name__, url_prefix='/api')

# MVP 阶段的硬编码汇率，后续可迁移到数据库
EXCHANGE_RATES = {
    'CNY': 1.0,
    'USD': 7.25,
    'HKD': 0.92,
}


@bp.get('/summary/')
def summary():
    """返回首页仪表盘所需的聚合数据，合并 positions + assets."""
    with get_db() as db:
        positions = db.query(Position).all()
        assets = db.query(Asset).filter(Asset.user_id == 1).all()

    total_assets_cny = 0.0
    total_pnl_cny = 0.0
    market_distribution = {}

    # 1. 交易性资产（positions）
    for p in positions:
        rate = EXCHANGE_RATES.get(p.currency, 1.0)
        market_value = p.quantity * p.current_price * rate
        total_assets_cny += market_value
        pnl = (p.current_price - p.avg_price) * p.quantity * rate
        total_pnl_cny += pnl

        market_distribution.setdefault(p.market, 0.0)
        market_distribution[p.market] += market_value

    # 2. 通用资产（assets）
    total_liabilities_cny = 0.0
    for a in assets:
        if a.major_category == 'liability':
            total_liabilities_cny += a.amount
        else:
            total_assets_cny += a.amount

    return jsonify(
        {
            'data': {
                'total_assets_cny': round(total_assets_cny, 2),
                'total_liabilities_cny': round(total_liabilities_cny, 2),
                'net_assets_cny': round(total_assets_cny - total_liabilities_cny, 2),
                'total_pnl_cny': round(total_pnl_cny, 2),
                'market_distribution': {k: round(v, 2) for k, v in market_distribution.items()},
            },
            'message': 'ok',
        }
    )

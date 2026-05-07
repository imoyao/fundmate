# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/7 21:52
# File : summary.py
# backend/app/api/summary.py
# -*- coding: utf-8 -*-
"""首页仪表盘聚合数据 API."""

from apiflask import APIBlueprint

from app.database import get_db
from app.models.position import Position

bp = APIBlueprint('summary', __name__, url_prefix='/api')

# MVP 阶段的硬编码汇率，后续可迁移到数据库
EXCHANGE_RATES = {
    'CNY': 1.0,
    'USD': 7.25,
    'HKD': 0.92,
}


@bp.get('/summary')
def summary():
    """返回首页仪表盘所需的聚合数据."""
    with get_db() as db:
        positions = db.query(Position).all()

    total_assets_cny = 0.0
    total_pnl_cny = 0.0
    market_distribution = {}

    for p in positions:
        rate = EXCHANGE_RATES.get(p.currency, 1.0)
        market_value = p.quantity * p.current_price * rate
        pnl = (p.current_price - p.avg_price) * p.quantity * rate
        total_assets_cny += market_value
        total_pnl_cny += pnl

        market_distribution.setdefault(p.market, 0.0)
        market_distribution[p.market] += market_value

    return {
        'total_assets_cny': round(total_assets_cny, 2),
        'total_pnl_cny': round(total_pnl_cny, 2),
        'market_distribution': {k: round(v, 2) for k, v in market_distribution.items()},
    }

# -*- coding: utf-8 -*-
"""探市（大类资产观察）API 路由（#1436 / #1444 收口实现）。

薄视图：仅做参数解析与信封封装，业务逻辑委托 MarketOverviewService。
"""

from apiflask import APIBlueprint
from flask import jsonify, request

from app.services.market_service import MarketOverviewService

market_bp = APIBlueprint('market', __name__, url_prefix='/api/market')


@market_bp.get('/overview')
def get_market_overview():
    """
    获取探市大类资产观察（20 个大类资产当日涨跌 + 相对位置）

    GET /api/market/overview

    Query Parameters:
        force: 是否强制刷新缓存（默认 false）。设 true 会清空本 namespace 缓存重新取数。

    Response:
      {
        "data": {
          "updated_at": "2026-09-12 23:00:00",
          "as_of_note": "各市场数据截止：A股 15:00 / 港股 16:00 / 美股 05:00（北京）……",
          "groups": [
            {"category": "A股", "assets": [
              {"key": "sh000001", "name": "上证指数", "category": "A股", "available": true,
               "change_pct": 0.85, "trade_date": "2026-09-12", "data_asof": "2026-09-12 15:00:11",
               "position": {"percentile": 41.2, "label": "适中", "basis": "价格分位", "window": 500},
               "caliber": null, "reason": null}
            ]},
            ...
          ],
          "unavailable_count": 6,
          "bond_yield": {"cn_10y": 1.85, "cn_10y_change_bp": -2.3, "us_10y": 4.12, "us_10y_change_bp": 1.1},
          "notes": ["...", "..."]
        },
        "message": "success"
      }

    不可得资产（缺源 / 用户决策占位）以 available=false + reason 软占位返回，不抛 500。
    """
    force = request.args.get('force', 'false').lower() in ('1', 'true', 'yes')
    data = MarketOverviewService.get_overview(force_refresh=force)
    return jsonify({'data': data, 'message': 'success'})

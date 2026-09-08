# -*- coding: utf-8 -*-
"""统一资产聚合搜索端点（#1286）。

前端全局搜索唯一后端入口：自选添加弹窗、探市添加区、未来组合购买记账录入
均经 `GET /api/search/assets/?q=` 搜全部品种（证券/基金/指数/投顾组合/基金经理）。
Provider 注册表见 app/services/asset_search.py，新增品种不改本端点。
"""

from apiflask import APIBlueprint
from flask import jsonify, request

from app.core.database import get_db
from app.services.asset_search import search_assets_aggregate

bp = APIBlueprint('search', __name__, url_prefix='/api/search')


@bp.get('/assets/')
def search_assets():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'data': [], 'message': 'ok'})
    with get_db() as db:
        results = search_assets_aggregate(db, q)
    return jsonify({'data': results, 'message': 'ok'})

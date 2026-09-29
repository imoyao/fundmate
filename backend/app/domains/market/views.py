# -*- coding: utf-8 -*-
"""探市（大类资产观察）API 路由（#1436 / #1444 收口实现）。

薄视图：仅做参数解析与信封封装。读库优先 + 兜底回写的编排在
`app.services.market_snapshot_store.resolve_overview` 完成（#1460 / #1606）。
"""

from apiflask import APIBlueprint
from flask import jsonify, request

from app.services.market_snapshot_store import resolve_overview

market_bp = APIBlueprint('market', __name__, url_prefix='/api/market')


@market_bp.get('/overview/', strict_slashes=False)
def get_market_overview():
    """
    获取探市大类资产观察（20 个大类资产当日涨跌 + 相对位置）

    GET /api/market/overview

    Query Parameters:
        force: 是否强制刷新（默认 false）。设 true 会绕过库内快照重新取数。

    Response:
      {"data": {"updated_at": "...", "as_of_note": "...", "groups": [...],
                "unavailable_count": 6, "bond_yield": {...},
                "from_snapshot": true, "snapshot_date": "2026-09-12"},
       "message": "success"}

    不可得资产以 available=false + reason 软占位返回，不抛 500；
    from_snapshot=true 表示响应来自库内日频快照（排障用）。
    """
    force = request.args.get('force', 'false').lower() in ('1', 'true', 'yes')
    data = resolve_overview(force)
    return jsonify({'data': data, 'message': 'success'})

# -*- coding: utf-8 -*-
"""探市（大类资产观察）API 路由（#1436 / #1444 收口实现）。

薄视图：仅做参数解析与信封封装。读库优先 + 兜底回写的编排在
`app.services.market_snapshot_store.resolve_overview` 完成（#1460 / #1606）。
"""

from apiflask import APIBlueprint
from flask import jsonify, request

from app.core.database import get_db
from app.core.exceptions import ErrorCode, SBException
from app.services.industry_emotion_service import get_latest_industry_emotion
from app.services.industry_pbroe_service import get_latest_industry_pbroe
from app.services.market_history_service import DEFAULT_DAYS, resolve_asset_history
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


@market_bp.get('/asset/<asset_key>/history/', strict_slashes=False)
def get_market_asset_history(asset_key: str):
    """
    获取单个大类资产的日线历史（探市·资产详情曲线，#1460 P2）

    GET /api/market/asset/<asset_key>/history

    Path Parameters:
        asset_key: 资产键（ASSET_CONFIG.key，如 sh000300 / HSI / .INX）

    Query Parameters:
        days: 回看交易日数（默认 500，范围 10~5000）
        force: 是否强制刷新（默认 false）。true 时绕过 30 分钟序列缓存重新取数

    Response:
      {"data": {"key": "sh000300", "name": "沪深300", "category": "A股",
                "points": [{"date": "2026-10-27", "close": 4123.45}, ...],
                "count": 500, "last_date": "2026-10-27",
                "total_rows": 4102, "expected_latest_date": "2026-10-28",
                "fetched": true, "added": 12, "stale": false, "reason": null},
       "message": "success"}

    首次请求会**按需回填**该资产全历史并落库，之后只补缺失日期（#1460 P2）。
    取数失败但库里有历史时正常返回，stale=true + reason 如实标注；
    既无历史又取数失败返回 503，未知 / 无源资产返回 404。
    单次只回填一个品种：不做「一次请求把 20 个资产全拉一遍」。
    """
    raw_days = request.args.get('days', str(DEFAULT_DAYS))
    try:
        days = int(raw_days)
    except (TypeError, ValueError):
        raise SBException(ErrorCode.INVALID_PARAMS.code, 'days 必须是整数', 400)
    force = request.args.get('force', 'false').lower() in ('1', 'true', 'yes')
    data = resolve_asset_history(asset_key, days=days, force=force)
    return jsonify({'data': data, 'message': 'success'})


@market_bp.get('/industry-pbroe/', strict_slashes=False)
def get_industry_pbroe():
    """行业 PB-ROE 散点矩阵（探市行业比较，#2481）。

    GET /api/market/industry-pbroe

    Response:
      {"data": {"title": "A股行业PB-ROE", "x_label": "ROE(%)", "y_label": "PB",
                "update_time": "2026-10-21",
                "series": [{"industry": "农林牧渔", "roe": 2.71, "pb": 2.4}, ...],
                "collected_at": "2026-10-21", "source": "jiucaishuo_pbroe"},
       "message": "success"}

    读库即回（日频快照由 sync/jobs/industry_pbroe_job.py 写入）；无快照时
    data=null，前端显示「暂无数据」。负 ROE 行业有效，不剔除；
    update_time 为上游数据日期，前端原样标注。
    """
    with get_db() as db:
        data = get_latest_industry_pbroe(db)
    return jsonify({'data': data, 'message': 'success'})


@market_bp.get('/industry-emotion/', strict_slashes=False)
def get_industry_emotion():
    """行业恐贪快照（探市「行业情绪」档，#2479）。

    GET /api/market/industry-emotion

    Response:
      {"data": {"updated_at": "2026-10-21",
                "items": [{"name": "军工PH值", "industry": "军工", "metric": "PH",
                           "value": 34.0, "history_days": 12}, ...],
                "source": "jiucaishuo_industry"},
       "message": "success"}

    快照 = 最新 collected_at 当日全部行；上游免登录端点每次只返回**轮换的少数
    行业**（2026-10-21 实测 4 条），行业清单逐日可能不同——前端如实呈现，
    不假设全集。metric（PH/TF）为上游原文后缀、语义未实证，仅透出不解读；
    history_days 为该指标自建历史的累积天数。无数据 data=null。
    """
    with get_db() as db:
        data = get_latest_industry_emotion(db)
    return jsonify({'data': data, 'message': 'success'})

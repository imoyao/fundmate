# -*- coding: utf-8 -*-
"""探市（大类资产观察）API 路由（#1436 / #1444 收口实现）。

薄视图：仅做参数解析与信封封装，业务逻辑委托 MarketOverviewService。

数据来源（#1460 P1）：**优先读库内日频快照**（毫秒级），库里没有完整当日数据时
才走实时取数并把结果回写，下次请求即可命中库。
"""

from typing import Any, Dict

from apiflask import APIBlueprint
from flask import jsonify, request
from loguru import logger

from app.core.database import market_session
from app.services.market_service import MarketOverviewService
from app.services.market_snapshot_store import load_overview_from_db, save_overview_to_db

market_bp = APIBlueprint('market', __name__, url_prefix='/api/market')


@market_bp.get('/overview/', strict_slashes=False)
def get_market_overview():
    """
    获取探市大类资产观察（20 个大类资产当日涨跌 + 相对位置）

    GET /api/market/overview

    Query Parameters:
        force: 是否强制刷新（默认 false）。设 true 会绕过库内快照、清空缓存重新取数。

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
          "notes": ["...", "..."],
          "from_snapshot": true,
          "snapshot_date": "2026-09-12"
        },
        "message": "success"
      }

    不可得资产（缺源 / 用户决策占位）以 available=false + reason 软占位返回，不抛 500。
    from_snapshot=true 表示本次响应来自库内日频快照而非实时取数（排障用）。
    """
    force = request.args.get('force', 'false').lower() in ('1', 'true', 'yes')
    data = _resolve_overview(force)
    return jsonify({'data': data, 'message': 'success'})


def _resolve_overview(force: bool) -> Dict[str, Any]:
    """读库优先：库里有完整当日快照就直接组装，否则实时取数并回写。

    读库 / 回写失败一律**静默降级**到实时路径：数据底座是加速手段，
    不该成为接口的新故障点（#1460）。
    """
    if not force:
        try:
            with market_session() as db:
                snapshot = load_overview_from_db(db)
            if snapshot:
                return snapshot
        except Exception as e:  # noqa: BLE001 - 快照不可用时降级为实时取数，不抛 500
            logger.warning('读大类资产快照失败，降级为实时取数: {}', e)

    overview = MarketOverviewService.get_overview(force_refresh=force)

    # 兜底回写：本次实时结果存下来，下次请求即可读库。
    # 不显式 commit —— 请求级事务由 teardown_request_session 统一提交（#1632）。
    try:
        with market_session() as db:
            save_overview_to_db(db, overview)
    except Exception as e:  # noqa: BLE001 - 回写失败不影响本次响应
        logger.warning('大类资产快照回写失败（不影响本次响应）: {}', e)
    return overview

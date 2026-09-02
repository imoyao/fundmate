# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/9/2
# File : views.py
"""通用用量 API（issue #823）.

独立、与业务域无关的用量查询端点：前端在进入受限功能（OCR 截图导入 / 持仓导入等）
前统一调用本接口展示余量与重置时间，超限时弹出升级提示。

路由：GET /api/usage/<feature>
    feature 取值（与 ai_recognizer.guards / registry 对齐）：
        ocr_import      OCR 截图导入（默认 5 次/天）
        txn_import      交易记录导入
        holding_import  持仓截图导入
        scheduled_sync  定时同步（规划中）
    feature 透传给 guards.check_usage，未知 feature 不会 400（与历史别名实现行为一致）。

鉴权：非白名单接口，需登录；当前用户从 g.current_user 取（core/auth.py 注入）。
注意：本端点为只读查询，但 guards.check_usage 在当日行不存在时会建行（used=0），
与历史实现行为一致——仅产生一条 0 用量的占位行，无副作用风险。
"""

from datetime import date, timedelta

from apiflask import APIBlueprint
from flask import g, jsonify

from app.core.exceptions import SBException
from app.services.ai_recognizer import guards

usage_bp = APIBlueprint('usage', __name__, url_prefix='/api/usage')


def _current_user_id() -> int:
    user = getattr(g, 'current_user', None)
    if user is None:
        raise SBException(code=1005, message='未授权，请先登录', status_code=401)
    return user.id


@usage_bp.get('/<feature>')
def get_usage(feature: str):
    """查询某功能当日用量（used/quota/remaining/重置时间）.

    返回结构：
        {
          "data": {
            "feature": "ocr_import",
            "used": 0,
            "quota": 5,
            "remaining": 5,
            "period_date": "2026-09-02",
            "reset_at": "2026-09-03"
          },
          "message": "ok"
        }
    reset_at 为下次重置日（period_date 的次日），前端据此展示「明日 0 点重置」。
    """
    user_id = _current_user_id()
    info = guards.check_usage(user_id, feature=feature)
    info['feature'] = feature
    # 重置时间：按自然日配额，次日 0 点重置
    try:
        period = date.fromisoformat(info['period_date'])
        info['reset_at'] = (period + timedelta(days=1)).isoformat()
    except (ValueError, KeyError, TypeError):
        info['reset_at'] = None
    return jsonify({'data': info, 'message': 'ok'})

# -*- coding: utf-8 -*-
"""Flask 集成层：薄装饰器，迁移到 FastAPI 时换成 Dependency 即可，核心逻辑复用。"""

from functools import wraps

from flask import abort, g

from app.core.database import get_session
from app.services.entitlement_check import PRO_FEATURES, check_entitlement, get_pro_status


def require_pro_feature(feature: str):
    """装饰器：挂在 Flask 端点上，校验家庭是否拥有该 Pro 功能权益。

    Args:
        feature: 功能键，必须在 PRO_FEATURES 白名单中

    Raises:
        ValueError: feature 未登记（开发期拦截）
        403: 权益未开通或已过期，响应统一错误信封
    """
    if feature not in PRO_FEATURES:
        raise ValueError(f'未登记的 Pro 功能：{feature}（需先加入 PRO_FEATURES 白名单）')

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            family_id = getattr(g, 'family_id', 1)
            with get_session() as db:
                result = check_entitlement(db, family_id, feature)

            if not result.granted:
                # 统一错误信封：前端据此渲染付费墙/引导
                abort(403, description={
                    'data': None,
                    'message': 'Pro 功能未开通',
                    'error_code': 1006,  # FORBIDDEN
                    'detail': {
                        'feature': feature,
                        'reason': result.reason,
                        'expires_at': result.expires_at,
                    }
                })
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def get_pro_status_for_family(family_id: int) -> dict:
    """供 /pro/ 端点调用：一次性返回所有 feature 的状态位。"""
    with get_session() as db:
        return get_pro_status(db, family_id)

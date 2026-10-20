# -*- coding: utf-8 -*-
"""Flask 集成层：薄装饰器，迁移到 FastAPI 时换成 Dependency 即可，核心逻辑复用。"""

from functools import wraps

from flask import g

from app.core import database
from app.core.exceptions import ErrorCode, SBException
from app.services.entitlement_check import PRO_FEATURES, check_entitlement, get_pro_status


def require_pro_feature(feature: str):
    """装饰器：挂在 Flask 端点上，校验家庭是否拥有该 Pro 功能权益。

    Args:
        feature: 功能键，必须在 PRO_FEATURES 白名单中

    Raises:
        ValueError: feature 未登记（开发期拦截）
        SBException: 权益未开通或已过期（403 / error_code=1007）

    为什么用独立错误码而不是复用 FORBIDDEN（#2324 收口）：403 在本仓还承载
    「viewer 只读」等语义，前端只凭状态码分不清「该升级」与「没权限做这件事」。
    独立码让前端能直接渲染权益态；``detail`` 走响应信封的 ``data`` 字段，
    ``message`` 保持字符串——旧实现把整个 dict 塞进 ``abort(description=...)``，
    经 ``main.py`` 的 HTTPException 处理器后会让 ``message`` 变成对象，违反
    ``{data, message, error_code}`` 契约。
    """
    if feature not in PRO_FEATURES:
        raise ValueError(f'未登记的 Pro 功能：{feature}（需先加入 PRO_FEATURES 白名单）')

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            family_id = getattr(g, 'family_id', 1)
            with database.get_session() as db:
                result = check_entitlement(db, family_id, feature)

            if not result.granted:
                raise SBException(
                    code=ErrorCode.PRO_NOT_ENTITLED.code,
                    message=ErrorCode.PRO_NOT_ENTITLED.msg,
                    status_code=ErrorCode.PRO_NOT_ENTITLED.http_status,
                    detail={
                        'feature': feature,
                        'reason': result.reason,
                        'expires_at': result.expires_at,
                    },
                )
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def get_pro_status_for_family(family_id: int) -> dict:
    """供 /pro/ 端点调用：一次性返回所有 feature 的状态位。"""
    with database.get_session() as db:
        return get_pro_status(db, family_id)

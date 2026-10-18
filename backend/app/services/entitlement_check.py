# -*- coding: utf-8 -*-
"""权益核心校验逻辑（纯函数，零框架耦合，可迁移到 FastAPI 复用）。

设计原则：
- 白名单制：未显式登记的 feature 默认拒绝（fail-closed）
- 纯业务逻辑：无 Flask/FastAPI 依赖，仅依赖 SQLAlchemy Session
- 单一事实源：Entitlement 表是唯一权威
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import ErrorCode, SBException
from app.domains.entitlements.models import Entitlement

# 白名单：显式登记才放行；新增 Pro 模块必须在此注册，否则默认拒绝
PRO_FEATURES = frozenset({
    'pro-insight',
    'pro-risk',
    'pro-allocation',
    'pro-status',
})


@dataclass(frozen=True)
class EntitlementResult:
    """校验结果载体。"""
    granted: bool
    expires_at: Optional[str] = None  # ISO8601 or None
    reason: Optional[str] = None      # 'ok' | 'not_granted' | 'expired'


def check_entitlement(db: Session, family_id: int, feature: str) -> EntitlementResult:
    """核心校验：纯业务逻辑，零框架耦合。

    Args:
        db: SQLAlchemy Session（已按数据域路由到 user 域）
        family_id: 家庭 ID
        feature: 功能键，必须在 PRO_FEATURES 白名单中

    Returns:
        EntitlementResult: granted=True 表示放行；False 附带 reason 供前端渲染付费墙

    Raises:
        SBException: feature 不在白名单中（400 INVALID_PARAMS）
    """
    if feature not in PRO_FEATURES:
        raise SBException(
            code=ErrorCode.INVALID_PARAMS.code,
            message=f'未知的 Pro 功能：{feature}',
            status_code=400,
        )

    row = db.query(Entitlement).filter(
        Entitlement.family_id == family_id,
        Entitlement.feature == feature,
    ).first()

    if not row or not row.granted:
        return EntitlementResult(granted=False, reason='not_granted')

    if row.expires_at and row.expires_at < datetime.utcnow():
        return EntitlementResult(
            granted=False,
            expires_at=row.expires_at.isoformat(),
            reason='expired',
        )

    return EntitlementResult(
        granted=True,
        expires_at=row.expires_at.isoformat() if row.expires_at else None,
        reason='ok',
    )


def get_pro_status(db: Session, family_id: int) -> dict:
    """一次性返回所有 Pro 功能的状态位（供 /pro/ 端点）。

    未登记的 feature 默认 granted=False。
    """
    rows = db.query(Entitlement).filter(
        Entitlement.family_id == family_id,
        Entitlement.feature.in_(PRO_FEATURES),
    ).all()
    granted_map = {r.feature: r for r in rows}

    result = {}
    for f in PRO_FEATURES:
        row = granted_map.get(f)
        result[f] = {
            'granted': row.granted if row else False,
            'expires_at': row.expires_at.isoformat() if row and row.expires_at else None,
        }
    return result

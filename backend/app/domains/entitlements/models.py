# -*- coding: utf-8 -*-
"""权益模型：家庭级 Pro 功能开通记录。

- `family_id` 家庭作用域：权益随家庭共享，非用户私有
- `feature` 功能键：白名单制（见 services/entitlement_check.PRO_FEATURES）
- `granted` / `expires_at`：布尔开关 + 可选过期时间（订阅制预留）
- `source`：来源标记，便于运营审计（manual / subscription / trial）
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class Entitlement(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'entitlements'
    __table_args__ = (UniqueConstraint('family_id', 'feature', name='uq_family_feature'),)

    family_id = Column(
        Integer,
        ForeignKey('families.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='归属家庭',
    )
    feature = Column(String(50), nullable=False, comment='功能键：pro-insight / pro-risk / pro-allocation / pro-status')
    granted = Column(Boolean, default=False, nullable=False, comment='是否开通')
    granted_at = Column(DateTime, nullable=True, comment='开通时间')
    expires_at = Column(DateTime, nullable=True, comment='过期时间（订阅制预留，永久制留空）')
    source = Column(String(20), default='manual', comment='来源：manual / subscription / trial')

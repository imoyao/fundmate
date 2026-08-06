# -*- coding: utf-8 -*-
"""家庭模型（多用户家庭共享层，D1）。

家庭是账本数据的归属容器：核心业务表按 `family_id` 归属家庭，成员共享同一套账本。
创建家庭时创建者自动成为该家庭主理人（admin）。
"""

from sqlalchemy import Column, String

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class Family(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'families'

    name = Column(String(100), nullable=False, comment='家庭名称')

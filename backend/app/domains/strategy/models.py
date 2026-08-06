# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/13 19:57
# File : models.py
# -*- coding: utf-8 -*-
"""
策略标签模型 — 用于持仓风格分析（不影响 XIRR 计算）
"""

from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint

from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin


class StrategyTag(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    __tablename__ = 'strategy_tags'

    name = Column(String(50), nullable=False, unique=True, comment='标签名称（如"成长"）')


class PositionStrategyTag(Base, PrimaryKeyMixin, FamilyScopedMixin):
    __tablename__ = 'position_strategy_tags'
    __table_args__ = (UniqueConstraint('position_id', 'strategy_tag_id', name='uq_position_strategy_tag'),)

    position_id = Column(Integer, ForeignKey('positions.id', ondelete='CASCADE'), nullable=False, comment='持仓ID')
    strategy_tag_id = Column(
        Integer, ForeignKey('strategy_tags.id', ondelete='CASCADE'), nullable=False, comment='策略标签ID'
    )

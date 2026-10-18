# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/13 19:57
# File : models.py
# -*- coding: utf-8 -*-
"""
策略标签模型 — 用于持仓风格分析（不影响 XIRR 计算）
"""

from sqlalchemy import Column, ForeignKey, Integer, Numeric, String, UniqueConstraint

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


class TargetAllocation(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """目标配比（#2237）：用户给某个标的设定的**目标占比**（百分点）。

    数据准入四问（AGENTS.md「数据策略」要求留痕）：
      1. 谁在用？—— `GET /api/strategy/allocation/` 的偏离结果（前端配比设置 UI），
         以及配比偏离提醒（走 #2236 通知底座，铃铛 + 首页可见）。
      2. 什么场景用？—— 用户设定「沪深300 目标 40%」后，占比漂移超过阈值时被告知
         「你偏离了自己定的规矩」。
      3. 缺了会怎样？—— 目标无处存、偏离无从算，再平衡提醒（#873 的核心诉求）无法落地。
      4. 成本多大？—— 每家庭每标的 1 行；计算为本地聚合，零外部请求。

    为什么按 `symbol` 而不按持仓行（position_id）：配比描述的是「这个标的该占多少」，
    同一标的分散在多个账户是常态；按持仓行会让用户重复配置且口径随账户拆分漂移。

    不强制多条之和 = 100：允许用户只给部分标的设目标（其余为「未设目标」），
    强行要求配平会让「先给两只核心持仓定规矩」这件小事变得无法开始。
    """

    __tablename__ = 'target_allocations'

    symbol = Column(String(30), nullable=False, comment='标的代码（与 positions.symbol 同字面量）')
    target_weight = Column(Numeric(5, 2), nullable=False, comment='目标占比（百分点，0~100）')
    notes = Column(String(200), nullable=True, comment='备注（如「核心仓，长期不动」）')

    __table_args__ = (UniqueConstraint('family_id', 'symbol', name='uq_target_allocation_family_symbol'),)

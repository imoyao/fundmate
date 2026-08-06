# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/13 17:52
# File : models.py
# -*- coding: utf-8 -*-
"""
投资组合模型
"""

from sqlalchemy import Boolean, Column, Date, Numeric, String

from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin


class Portfolio(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    __tablename__ = 'portfolios'

    name = Column(String(100), nullable=False, comment='组合名称')
    description = Column(String(500), comment='组合描述')
    purpose = Column(String(200), comment='投资目的（如“养老金”）')
    target_return = Column(Numeric(5, 2), comment='年化目标收益率（%）')
    target_amount = Column(Numeric(15, 2), comment='目标金额')
    target_date = Column(Date, comment='目标日期')
    benchmark = Column(String(50), comment='基准指数（如 CSI300）')
    is_deleted = Column(Boolean, default=False, comment='软删除标记')

# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 10:56
# File : models.py
"""资金容器/账户模型"""

from sqlalchemy import Column, String

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class Ledger(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'ledgers'

    name = Column(String(50), nullable=False, comment='容器名称，如"华泰证券"、"支付宝基金"')
    ledger_type = Column(String(20), default='general', comment='类型: general/cash/family')
    currency = Column(String(3), default='CNY')
    notes = Column(String(200))

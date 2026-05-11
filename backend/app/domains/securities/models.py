# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/11 18:47
# File : models.py
# app/domains/securities/models.py

"""证券元数据模型（股票、ETF、可转债、期货等）"""

from sqlalchemy import Column, String

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class Security(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'securities'

    symbol = Column(String(30), unique=True, nullable=False, comment='代码，如 00700.HK, BTC-USD')
    name = Column(String(100), nullable=False, comment='名称')
    market = Column(String(20), nullable=False, comment='市场: CN_A, CN_HK, US, CRYPTO, COMMODITY')
    type = Column(String(20), nullable=False, comment='产品类型: stock, etf, bond, future, crypto')
    currency = Column(String(10), default='CNY', comment='交易币种')
    sector = Column(String(50), comment='行业/板块')

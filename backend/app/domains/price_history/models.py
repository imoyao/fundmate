# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:21
# File : models.py
# -*- coding: utf-8 -*-
# app/domains/price_history/models.py

"""证券历史行情数据模型"""

from sqlalchemy import Column, Date, Float, ForeignKey, Index, Integer, String

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class PriceHistory(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'price_history'

    security_id = Column(
        Integer,
        ForeignKey('securities.id', ondelete='CASCADE'),
        nullable=False,
        comment='关联证券ID',
    )
    symbol = Column(String(30), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, comment='交易日期')
    open = Column(Float, comment='开盘价')
    high = Column(Float, comment='最高价')
    low = Column(Float, comment='最低价')
    close = Column(Float, nullable=False, comment='收盘价')
    volume = Column(Float, comment='成交量')
    adj_close = Column(Float, comment='复权收盘价（后复权）')
    source = Column(String(20), default='akshare', comment='数据源')

    # 复合唯一索引
    __table_args__ = (
        Index('ix_ph_symbol_date', 'symbol', 'trade_date', unique=True),  # 主查询索引 + 唯一约束
        Index('ix_ph_security_id', 'security_id'),  # 按 security_id 查询的索引
    )

# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/9 19:23
# File : models.py


from sqlalchemy import Column, Date, Float, Integer, String, Text

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class Transaction(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'transactions'

    position_id = Column(Integer)
    txn_type = Column('type', String(20))
    trade_date = Column(Date)  # 交易发起日期 (T日)
    quantity = Column(Float)  # 操作数量 (股/张/份)
    price = Column(Float)  # 操作价格 (成交价)
    fee = Column(Float, default=0.0)  # 手续费
    amount = Column(Float)  # 操作总金额
    status = Column(String(20), default='success')
    position_name = Column(String(100))
    account_name = Column(String(100))
    confirm_date = Column(Date)  # 确认日期 (到账日)
    notes = Column(Text)  # 复盘备注

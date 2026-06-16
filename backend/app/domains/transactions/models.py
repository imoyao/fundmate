# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/9 19:23
# File : models.py
"""
维度	status	新增字段
含义	交易是否成功执行	记录在系统中的处理阶段
现有值	success	无
未来新值	failed（执行失败）
processing（执行中）	orphan（孤立未关联）
pending（待确认，如基金 T+1）
confirmed（已确认）
关系	一条孤立的卖出记录，交易本身是成功的	但它关联不到持仓，需要标记处理阶段
"""

from sqlalchemy import Column, Date, DateTime, Integer, String, Text

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class Transaction(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'transactions'

    position_id = Column(Integer)
    symbol = Column(String(30), nullable=True, comment='资产代码快照')
    txn_type = Column('type', String(20))
    trade_date = Column(DateTime, comment='交易发起日(T日)，秒级')
    quantity = Column(Integer, default=0, comment='操作数量(0.0001份/单位)')
    price = Column(Integer, default=0, comment='成交价(分)')
    confirm_date = Column(Date, comment='确认日期')
    fee = Column(Integer, default=0, comment='手续费(分)')
    amount = Column(Integer, default=0, comment='交易总金额(分)')
    status = Column(String(20), default='success')
    entry_status = Column(String(20), nullable=True)
    link_group_id = Column(String(36), nullable=True, comment='关联交易组ID')
    position_name = Column(String(100))
    asset_type = Column(String(20), nullable=True, default=None, comment='资产类型快照')
    account_name = Column(String(100))
    import_hash = Column(String(64), nullable=True, comment='导入去重哈希值')
    notes = Column(Text)

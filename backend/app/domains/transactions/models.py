# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/9 19:23
# File : models.py


from sqlalchemy import Column, Date, Float, Integer, String, Text

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin

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
    entry_status = Column(String(20), nullable=True)  # 记录处理阶段（orphan/pending/confirmed）
    link_group_id = Column(String(36), nullable=True, comment='关联交易组ID，用于绑定同一业务的多笔记录')
    position_name = Column(String(100))
    account_name = Column(String(100))
    confirm_date = Column(Date)  # 确认日期 (到账日)
    import_hash = Column(String(64), nullable=True, comment='导入去重哈希值')
    notes = Column(Text)  # 复盘备注

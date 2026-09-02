# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 17:20
# File : models.py
# -*- coding: utf-8 -*-
"""通用资产模型 — 覆盖除交易性金融资产外的所有资产/负债."""

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)

from app.core.database import Base


class Asset(Base):
    __tablename__ = 'assets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=1, comment='用户 ID')
    family_id = Column(Integer, nullable=False, default=1, index=True, comment='归属家庭 ID（家庭共享层隔离键）')

    # 与账户的外键关联
    ledger_id = Column(
        Integer,
        ForeignKey('ledgers.id', ondelete='RESTRICT'),
        nullable=True,
        comment='关联账户ID',
    )
    account_name = Column(String(50), nullable=True, comment='所属账户名称（冗余快照）')

    major_category = Column(
        String(20),
        nullable=False,
        comment='大类：cash(流动资金)/fixed(固定资产)/investment(投资理财)/receivable(应收款)/liability(负债)/insurance(保险)/real_estate(房产)/precious_metal(贵金属)/custom(自定义)/bank_wealth(银行理财)/advisory(投顾)/trust(信托)/private_fund(私募)/wealth_insurance(理财型保险)',
    )
    minor_category = Column(
        String(50),
        nullable=True,
        comment='小类，自由输入，如 credit_card/mortgage/huabei/house/car/gold/personal_loan/social_insurance',
    )

    name = Column(String(200), comment='资产名称，如"招商银行房贷"')
    amount = Column(Integer, default=0, comment='当前价值/余额（单位：分）')
    currency = Column(String(3), default='CNY')

    allocation = Column(String(20), default='longterm', comment='配置目标（五笔钱）')
    status = Column(String(20), default='active', comment='active / closed')
    notes = Column(String(500), nullable=True)

    start_date = Column(Date, nullable=True, comment='购入/生效/起息日')
    end_date = Column(Date, nullable=True, comment='到期/还清日')

    extra = Column(JSON, nullable=True, comment='扩展属性')
    """
    # 扩展属性（JSON，存放各类资产的专属信息）
    # 例如：{"area": 120, "address": "xxx"} 用于房产
    #      {"license_plate": "京A12345"} 用于汽车
    #      {"borrower": "张三", "due_date": "2026-12-31"} 用于借款
    #      {"sum_insured": 500000, "premium": 5000, "period": "yearly"} 用于保险
    """

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # 索引
    __table_args__ = (
        Index('idx_assets_ledger_id', 'ledger_id'),
        Index('idx_assets_account_name', 'account_name'),
    )

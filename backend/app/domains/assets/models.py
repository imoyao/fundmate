# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 17:20
# File : models.py
# -*- coding: utf-8 -*-
"""通用资产模型 — 覆盖除交易性金融资产外的所有资产/负债."""

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Asset(Base):
    __tablename__ = 'assets'

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 用户（MVP 阶段默认 1，未来多用户时改动）
    user_id: Mapped[int] = mapped_column(Integer, default=1, comment='用户 ID')

    # 大类：cash / fixed / receivable / liability / insurance / custom
    major_category: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment='大类：cash(流动资金), fixed(固定资产), receivable(应收款), liability(负债), insurance(保险), custom(自定义)',
    )
    # 小类：信用卡、房贷、花呗、房产、汽车、黄金、个人借款、社保、商业保险 ……
    minor_category: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment='小类，自由输入，如 credit_card/mortgage/huabei/house/car/gold/personal_loan/social_insurance …',
    )

    # 基本描述
    name: Mapped[str] = mapped_column(String(200), comment='资产名称，如"招商银行房贷"')
    amount: Mapped[float] = mapped_column(Float, default=0.0, comment='当前价值/余额（元）')
    currency: Mapped[str] = mapped_column(String(3), default='CNY')

    # 归属
    account_name: Mapped[str | None] = mapped_column(String(50), comment='所属账户，如"招商银行"')
    allocation: Mapped[str | None] = mapped_column(String(20), default='longterm', comment='配置目标（五笔钱）')

    # 状态
    status: Mapped[str] = mapped_column(String(20), default='active', comment='active / closed')
    notes: Mapped[str | None] = mapped_column(String(500))

    # 时间
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment='购入/生效/起息日')
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment='到期/还清日')

    # 扩展属性（JSON，存放各类资产的专属信息）
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment='扩展属性')
    # 例如：{"area": 120, "address": "xxx"} 用于房产
    #      {"license_plate": "京A12345"} 用于汽车
    #      {"borrower": "张三", "due_date": "2026-12-31"} 用于借款
    #      {"sum_insured": 500000, "premium": 5000, "period": "yearly"} 用于保险

    # 审计
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

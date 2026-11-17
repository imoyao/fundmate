# -*- coding: utf-8 -*-
"""家庭财务规划配置模型。

对标 `dividends.models.DividendTarget`：一家庭一条（UniqueConstraint(family_id)），
FamilyScopedMixin 提供 family_id 并按家庭隔离。金额存整数分（与 assets/transactions 同惯例），
null 语义 = 用户尚未填报该项（不是 0 元）——前端据此显示「待配置」而非算出 0%。
"""

from sqlalchemy import BigInteger, Column, UniqueConstraint

from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin


class FamilyFinancialPlan(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """家庭财务规划：预估年支出 / 预估年收入，用于财务晴雨表的自由度指标。

    两个字段都可空：`None` 表示用户未配置该项，自由度分子虽可算（可投资资产×3%），
    但分母缺失时整个比率不可算，前端显示「填入年支出/年收入后显示」而非 0%。
    """

    __tablename__ = 'family_financial_plans'
    __table_args__ = (UniqueConstraint('family_id', name='uq_family_financial_plan_family'),)

    estimated_annual_expense_cents = Column(BigInteger, nullable=True, comment='预估年支出（分），null=未配置')
    estimated_annual_income_cents = Column(BigInteger, nullable=True, comment='预估年收入（分），null=未配置')

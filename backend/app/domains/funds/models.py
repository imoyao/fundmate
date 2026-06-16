# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11 19:31
# File : models.py
"""场外基金元数据模型"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class FundCompany(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'fund_companies'

    code = Column(String(20), unique=True, nullable=False, comment='公司编码')
    name = Column(String(60), nullable=False, comment='公司名称')
    full_name = Column(String(100), comment='全称')
    scale = Column(Float, comment='管理规模(亿)')


class FundVariety(Base, PrimaryKeyMixin):
    __tablename__ = 'fund_varieties'

    name = Column(String(50), unique=True, nullable=False, comment='大类名称')
    fund_types = relationship('FundType', back_populates='variety')


class FundType(Base, PrimaryKeyMixin):
    __tablename__ = 'fund_types'

    name = Column(String(50), unique=True, nullable=False, comment='类型名称')
    variety_id = Column(Integer, ForeignKey('fund_varieties.id'), comment='所属大类')
    variety = relationship('FundVariety', back_populates='fund_types')


class FundSaleOrg(Base, PrimaryKeyMixin):
    __tablename__ = 'fund_sales_orgs'

    org_id = Column(Integer, unique=True, comment='机构编号')
    name = Column(String(100), comment='机构名称')
    known_name = Column(String(50), comment='常用简称')


class Manager(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'managers'

    mgr_code = Column(String(30), unique=True, comment='管理人编码')
    name = Column(String(60), nullable=False, comment='姓名')
    mgr_type = Column(String(20), default='fund_manager', comment='类型: fund_manager, portfolio_manager, individual')
    company_id = Column(Integer, ForeignKey('fund_companies.id'), comment='所属公司')
    appointment_date = Column(Date, comment='任职起始日')
    sum_scale = Column(Float, comment='管理资产规模(亿)')
    best_return = Column(Float, comment='最佳回报(%)')
    avatar_url = Column(String(300))

    funds = relationship('Fund', secondary='fund_managers', back_populates='managers')


class Fund(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'funds'

    fund_code = Column(String(6), unique=True, nullable=False, comment='基金代码')
    name = Column(String(80), nullable=False, comment='简称')
    full_name = Column(String(100), comment='全称')
    pinyin_abbr = Column(String(30), comment='拼音缩写')
    pinyin_full = Column(String(80), comment='拼音全称')
    fund_type_id = Column(Integer, ForeignKey('fund_types.id'), comment='基金小类')
    fund_variety_id = Column(Integer, ForeignKey('fund_varieties.id'), comment='基金大类')
    company_id = Column(Integer, ForeignKey('fund_companies.id'), comment='基金公司')
    risk_level = Column(Integer, comment='风险等级 1-5')
    is_fe_charge = Column(Boolean, default=False, comment='前端收费')
    benchmark = Column(String(200), comment='业绩比较基准')
    create_time = Column(Date, comment='成立日期')
    symbol_prefix = Column(String(10), comment='代码前缀')
    is_active = Column(Boolean, default=True, server_default=text('1'), comment='是否参与净值同步')
    last_nav_check = Column(DateTime, comment='最后一次净值检查时间')
    nav_fail_count = Column(Integer, default=0, comment='连续获取净值失败次数')

    fund_type = relationship('FundType', foreign_keys=[fund_type_id])
    variety = relationship('FundVariety', foreign_keys=[fund_variety_id])
    company = relationship('FundCompany', foreign_keys=[company_id])
    managers = relationship('Manager', secondary='fund_managers', back_populates='funds')
    daily_worth = relationship('DailyWorth', back_populates='fund', order_by='DailyWorth.date.desc()')
    money_fund_daily_worth = relationship(
        'MoneyFundDailyWorth', back_populates='fund', order_by='MoneyFundDailyWorth.date.desc()'
    )


class FundManager(Base, PrimaryKeyMixin):
    __tablename__ = 'fund_managers'

    fund_id = Column(Integer, ForeignKey('funds.id'), nullable=False)
    mgr_id = Column(Integer, ForeignKey('managers.id'), nullable=False)
    is_classic = Column(Boolean, default=False, comment='代表作品')
    start_date = Column(Date, comment='任职起始')
    end_date = Column(Date, comment='任职结束')


class DailyWorth(Base, PrimaryKeyMixin, TimestampMixin):
    """基金每日净值"""

    __tablename__ = 'daily_worth'

    fund_code = Column(String(6), ForeignKey('funds.fund_code'), nullable=False, comment='基金代码')
    date = Column(Date, nullable=False, comment='净值日期')
    unit_nav = Column(Numeric(18, 6), comment='单位净值（元），精度6位小数')
    acc_nav = Column(Numeric(18, 6), comment='累计净值（元），6位小数')

    fund = relationship('Fund', back_populates='daily_worth')

    __table_args__ = (UniqueConstraint('fund_code', 'date', name='uq_daily_worth_code_date'),)


class PurchaseRule(Base, PrimaryKeyMixin, TimestampMixin):
    """申购/认购费率阶梯的金额区间规则"""

    __tablename__ = 'purchase_rules'

    start_quota = Column(Integer, comment='起始金额(分)，包含')
    end_quota = Column(Integer, comment='结束金额(分)，不包含，NULL表示正无穷')


class RedeemRule(Base, PrimaryKeyMixin, TimestampMixin):
    """赎回费率阶梯的持有天数区间规则"""

    __tablename__ = 'redeem_rules'

    start_day = Column(Integer, nullable=False, default=0, comment='起始天数, 包含')
    end_day = Column(Integer, nullable=True, comment='结束天数, 不包含, NULL表示正无穷')


class FeeRatio(Base, PrimaryKeyMixin, TimestampMixin):
    """基金费率与规则的关联表"""

    __tablename__ = 'fee_ratios'

    fund_code = Column(String(6), ForeignKey('funds.fund_code'), nullable=False, comment='基金代码')
    fee_type = Column(String(20), nullable=False, comment='费率类型: subscribe/purchase/redeem/management')
    rate = Column(Numeric(10, 6), comment='费率(如0.015000=1.5%)')
    fee_amount = Column(Integer, comment='固定金额(分)，与rate互斥')
    purchase_rule_id = Column(Integer, ForeignKey('purchase_rules.id'), nullable=True)
    redeem_rule_id = Column(Integer, ForeignKey('redeem_rules.id'), nullable=True)


class MoneyFundDailyWorth(Base, PrimaryKeyMixin, TimestampMixin):
    """货币基金每日万份收益与七日年化"""

    __tablename__ = 'money_fund_daily_worth'

    fund_code = Column(String(6), ForeignKey('funds.fund_code'), nullable=False, comment='基金代码')
    date = Column(Date, nullable=False, comment='日期')
    nav_per_10k = Column(Integer, default=0, comment='万份收益(分)')
    annual_return_7d = Column(Float, comment='七日年化收益率(%)，精度0.0001')

    fund = relationship('Fund', back_populates='money_fund_daily_worth')

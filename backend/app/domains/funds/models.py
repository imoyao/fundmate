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
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin
from app.core.db_utils import SafeNumeric


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
    unit_nav = Column(SafeNumeric(18, 6), comment='单位净值（元），精度6位小数')
    acc_nav = Column(SafeNumeric(18, 6), comment='累计净值（元），精度6位小数')

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
    rate = Column(SafeNumeric(10, 6), comment='费率(如0.015000=1.5%)')
    fee_amount = Column(Integer, comment='固定金额(分)，与rate互斥')
    currency = Column(String(10), nullable=False, default='CNY', comment='计费币种(ISO 4217)，默认CNY')
    purchase_rule_id = Column(Integer, ForeignKey('purchase_rules.id'), nullable=True)
    redeem_rule_id = Column(Integer, ForeignKey('redeem_rules.id'), nullable=True)


class MoneyFundDailyWorth(Base, PrimaryKeyMixin, TimestampMixin):
    """货币基金每日万份收益与七日年化。

    nav_per_10k 语义（#863 复核）：存储单位为「元」——万份收益如 000198 余额宝
    2026-08-14 为 0.2233 元/万元/日。早期实现按「分」处理导致收益恒 0 的 bug 已修
    （见 money_fund_income.py 模块 docstring），此处类型从 Integer 修为小数精度。
    """

    __tablename__ = 'money_fund_daily_worth'

    fund_code = Column(String(6), ForeignKey('funds.fund_code'), nullable=False, comment='基金代码')
    date = Column(Date, nullable=False, comment='日期')
    nav_per_10k = Column(SafeNumeric(10, 4), default=0, comment='万份收益(元)，如 0.2233')
    annual_return_7d = Column(Float, comment='七日年化收益率(%)，精度0.0001')
    # #863 数据治理：写入来源/算法版本标记。存量旧数据在迁移脚本中置 'legacy_dirty'
    # （旧算法脏数据，需清空重建），新写入由 fund_nav_job / async_backfill 显式标 'v2_recalc'。
    # server_default='legacy_dirty' 保证新增行默认脏数据标记；存量 NULL 行由迁移脚本回填。
    source_version = Column(
        String(20),
        nullable=False,
        server_default='legacy_dirty',
        comment='数据来源版本（#863）：legacy_dirty/v2_recalc',
    )

    fund = relationship('Fund', back_populates='money_fund_daily_worth')

    __table_args__ = (UniqueConstraint('fund_code', 'date', name='uq_money_fund_daily_worth_code_date'),)


class AdvisorPortfolio(Base, PrimaryKeyMixin, TimestampMixin):
    """投顾/基金组合公开参照（market 域，Turso）。

    覆盖且慢/蛋卷/天天基金等平台的「投顾组合 / 实盘组合 / 基金组合」实体
    （如且慢「远足」「成长五剑」、蛋卷策略组合）。属公开、读多写少的参照数据，
    与用户私有 portfolios（组合归属）无关，落 market 域。

    用户侧「自选投顾」只存 platform+code 业务键（见 watchlist 设计），
    经 CrossDomainQuery 两步法回查本表，零跨域外键、零 SQL join。
    """

    __tablename__ = 'advisor_portfolios'

    code = Column(String(30), unique=True, nullable=False, comment='平台组合代码(且慢ZHxxxx/蛋卷CSIxxxx/天天基金combo)')
    platform = Column(String(20), nullable=False, comment='来源平台: QIEMAN/DANJUAN/TIANTIAN/YINGMI')
    name = Column(String(100), nullable=False, comment='组合名称')
    host = Column(String(60), comment='主理人')
    org_name = Column(String(100), comment='主理人所属机构/平台方')
    risk_level = Column(String(20), comment='风险等级')
    strategy_type = Column(String(40), comment='策略类型(均衡/进取/稳健)')
    cum_return = Column(Float, comment='累计收益(%)')
    annual_return = Column(Float, comment='年化收益(%)')
    running_days = Column(Integer, comment='运行天数')
    is_active = Column(Boolean, default=True, comment='是否在售/有效')

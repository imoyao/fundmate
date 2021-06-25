#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/2/13 17:50

from backend.fundmate.database import (
    Column,
    CreateDateModel,
    CRUDMixin,
    PkModel,
    UpsertMixin,
    db,
    reference_col,
    relationship,
)


class DailyWorth(PkModel, CreateDateModel):
    """每日净值（初始净值数据按照基金名称分表存储，然后我们需要合并表）
    1. 考虑分表，主键应该使用uuid
    2. uuid vs GUID
    3. ~~PkModel~~
    """
    price = Column(db.Float, comment='基金单日净值')
    date = Column(db.Date, comment='日期')
    fund_id = reference_col('funds',
                            column_kwargs={'comment':
                                           '基金编号'})  # TODO: 到底使用id还是使用基金的6位编码
    fund = relationship("Fund", uselist=False, back_populates="daily_worth")


class Fund(PkModel, UpsertMixin):
    """基金表"""
    __tablename__ = "funds"
    __table_args__ = {'comment': '基金表'}

    fund_code = Column(db.Integer, unique=True, comment='基金编码')
    name = Column(db.String(30), comment='基金名称')
    '''
    此处标准写法应该使用英文，但是可能导致查询啰嗦，所以使用拼音代替变量，后面变量作为列名自解释
    1. [python - Use alias for column name in SQLAlchemy - Stack Overflow]
    (https://stackoverflow.com/questions/37758128/use-alias-for-column-name-in-sqlalchemy)
    2. [mysql - Aliasing field names in SQLAlchemy model or underlying SQL table - Stack Overflow]
    (https://stackoverflow.com/questions/37420135/aliasing-field-names-in-sqlalchemy-model-or-underlying-sql-table)
    查询：
    [SQLAlchemy select 中的表别名、列别名 | Jeremy's blog](https://www.isyin.cn/note/2018-10-28-2249/)
    ```
    # 表别名：select * from my_customer_table as customer
    customer = my_customer_table.alias('customer')
    
    # 列别名 select user.name as username from user
    columns = [
        customer,
        user.c['name'].label('username')
    ]
    ```
    '''
    sxszm = Column('abbr_capital_initial_phonetic_alphabet',
                   db.String(30),
                   comment='缩写首字母拼音')
    qxpy = Column('full_capital_phonetic_alphabet',
                  db.String(60),
                  comment='全写拼音')
    f_type = Column('fund_type_id',
                    db.Integer,
                    db.ForeignKey('fund_type.id'),
                    comment='基金小类编号')
    f_var = Column('fund_variety_id',
                   db.Integer,
                   db.ForeignKey('fund_variety.id'),
                   comment='基金大类编号')
    co_id = Column(db.Integer,
                   db.ForeignKey('fund_company.id'),
                   comment='所属基金公司编号')
    create_time = Column(db.DateTime, comment='基金创建时间')
    '''基金、净值为一对一关系，所以需要对两者都添加`relationship` [Basic Relationship Patterns — SQLAlchemy 1.4 Documentation](
    https://docs.sqlalchemy.org/en/14/orm/basic_relationships.html#one-to-one) '''
    daily_worth = relationship('DailyWorth',
                               back_populates='fund',
                               uselist=False)


class FundSaleOrg(PkModel, UpsertMixin):
    """
    基金销售机构
    """
    org_id = Column(db.Integer, comment='机构编号')
    name = Column(db.String(30), comment='机构名称')
    known_name = Column(db.String(10), comment='广为人知的代号')
    addr = Column(db.String(50), comment='注册地')
    org_type = Column(db.String(30), comment='机构类型')
    date = Column(db.String(10), comment='核准时间')

    def as_name(self):
        return self.known_name or self.name


class FundMgr(PkModel):
    """relation between Fund and Mgr
    """
    __table_args__ = {'comment': '基金与经理关联表'}  # TODO: 关联表

    fund_id = Column(db.Integer, db.ForeignKey('funds.id'), comment='基金编号')
    mgr_id = Column(db.Integer, db.ForeignKey('mgrs.id'), comment='基金经理编号')
    start_date = Column(db.DateTime)
    end_date = Column(db.DateTime)


class FundCompany(PkModel, UpsertMixin):
    """基金公司表
    """
    code = Column(db.String(10), comment='基金公司编号')
    name = Column(db.String(30), comment='基金公司名称')
    create_date = Column(db.DateTime, comment='创建时间')
    scale = Column(db.Numeric(10, 2), nullable=True,
                   comment='资产规模(亿元) ')  # 长度10，精度2
    dpy = Column('abbr_capital_initial_phonetic_alphabet',
                 db.String(30),
                 comment='缩写首字母拼音')
    tx_eval = Column(db.Integer, nullable=True, comment='天相评级（五星制）')
    full_name = Column(db.String(30), comment='基金公司全称')
    f_counts = Column(db.Integer, comment='拥有基金数量（参考值）')
    mgr = Column(db.String(10), comment='总经理')
    update_time = Column(db.DateTime, comment='数据更新时间')
    last_modified = Column(
        db.TIMESTAMP,
        nullable=False,
        server_default=db.text(
            "CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment='数据上次更新时间')


class FundType(PkModel):
    __table_args__ = {'comment': '基金小类表'}

    name = Column(db.String(255), unique=True)
    var_id = Column(db.Integer,
                    db.ForeignKey('fund_variety.id'),
                    comment='基金大类编号')


class FundVariety(PkModel, CRUDMixin):
    """
    根据投资对象的不同，可以将其分为股票型基金、债
    券型基金、混合型基金和货币型基金。根据证监会对基金
    的分类标准，股票型基金是指基金资产 80% 以上投资于股
    票的基金；80% 以上基金资产投资于债券的基金为债券型
    基金。混合型基金是指以股票、债券等为投资对象的基金，
    混合基金根据股、债资产投资比例及其投资策略又可分为
    偏股型基金、偏债型基金、平衡型基金等。货币型基金主
    要投资于国债、央行票据、银行定期存单、同业存款等低
    风险的短期有价证券（一般期限在一年以内，平均期限
    120 天）。
    根据运作方式的不同，可分为开放式基金和封闭式基金。
    根据投资地域的不同，可分为投资国内证券市场的 A
    股 基 金 和 投 资 境 外 市 场 的 QDII（Qualified Domestic
    Institutional Investor，即合格境内机构投资者）基金。
    根据投资策略的不同，可分为主动基金和被动基金。
    主动基金是基金管理人主动管理，以取得超越市场的业绩
    表现为目标的一种基金，需要由基金经理对证券市场进行
    深入研究，主动选择投资品种来确定投资组合。被动基金
    一般指的是指数基金。
    参见：《基金投资者权益保护读本》 P28
        投资者入市手册（基金篇） P15
    """
    __table_args__ = {'comment': '基金大类表'}
    '''
    如果要显示为 django model 中的 choices 类型，可以参考：
    [How to Create Django Like Choices Field in Flask SQLAlchemy | by Erika Dike | The Andela Way | Medium](https://medium.com/the-andela-way/how-to-create-django-like-choices-field-in-flask-sqlalchemy-1ca0e3a3af9d)
    [python - Best way to do enum in Sqlalchemy? - Stack Overflow](https://stackoverflow.com/questions/2676133/best-way-to-do-enum-in-sqlalchemy/2676213)
    '''
    name = Column(db.String(255), unique=True)


class InRule(PkModel):
    """这个问题比较复杂，需要后期再去设计
    可以直接记录结束点，然后每个出入都有3-4条记录，记录字段：分割点、费率、f_code
    """
    start_quota = Column(db.Integer, comment='计费开始额度')
    end_quota = Column(db.Integer, comment='计费结束额度')


class OutRule(PkModel):
    __table_args__ = {'comment': '赎回规则'}

    start_day = Column(db.Integer, comment='计费开始天数')
    end_day = Column(db.Integer, comment='计费结束天数')


class FundRate(PkModel):
    __table_args__ = {'comment': '费率记录'}

    fund_id = Column(db.Integer, db.ForeignKey('funds.id'), comment='基金编号')
    rule_id = Column(db.Integer, comment='费率编号')
    rate = Column(db.Integer, comment='费率百分比')
    type = Column(db.Boolean, nullable=True, comment='卖出或买入')  # TODO:多态关联


class Mgr(PkModel):
    __tablename__ = "mgrs"
    __table_args__ = {'comment': '基金经理'}

    mgr_id = Column(db.Integer, comment='经理编号（以天天基金为准）')
    name = Column(db.String(4), comment='经理名称')
    company_id = Column(db.Integer,
                        db.ForeignKey('fund_company.id'),
                        comment='所属公司ID')


class FundPortfolio(PkModel):
    """
    基金组合，爬取一些具有代表性的组合
    """
    pass


class FundPortfolioDetail(PkModel):
    """
    组合调仓记录
    """
    pass

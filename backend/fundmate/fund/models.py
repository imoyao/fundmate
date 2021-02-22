#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Administrator at 2021/2/13 17:50

from backend.fundmate.database import Column, CreateDateModel, PkModel, db, reference_col, relationship


class DailyWorth(PkModel, CreateDateModel):
    """每日净值"""
    price = Column(db.Float, comment='基金单日净值')
    date = Column(db.Date, comment='日期')
    # fund_id = reference_col(db.Integer, db.ForeignKey('funds.id'), comment='基金编号')
    fund_id = reference_col('funds', column_kwargs={'comment': '基金编号'})
    fund = relationship('Fund', back_populates='daily_worth')


class Fund(PkModel):
    """基金表"""
    __tablename__ = "funds"
    __table_args__ = {'comment': '基金表'}

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
    fund_code = Column(db.Integer, unique=True, comment='基金编码')
    ftype = Column('fund_type_id',
                   db.Integer,
                   db.ForeignKey('fund_type.id'),
                   comment='基金小类编号')
    fvar = Column('fund_variety_id',
                  db.Integer,
                  db.ForeignKey('fund_variety.id'),
                  comment='基金大类编号')
    co_id = Column(db.Integer,
                   db.ForeignKey('fund_company.id'),
                   comment='所属基金公司编号')
    create_time = Column(db.DateTime, comment='基金创建时间')


class FundRate(PkModel):

    fund_id = Column(db.Integer, db.ForeignKey('funds.id'), comment='基金编号')
    rule_id = Column(db.Integer, comment='费率编号')
    rate = Column(db.Integer, comment='费率百分比')
    type = Column(db.Boolean, nullable=True, comment='卖出或买入')  # TODO:多态关联


class FundMgr(PkModel):
    """relation between Fund and Mgr
    """
    __table_args__ = {'comment': '基金与经理关联表'}        # TODO: 关联表

    fund_id = Column(db.Integer, db.ForeignKey('funds.id'), comment='基金编号')
    mgr_id = Column(db.Integer, db.ForeignKey('mgrs.id'), comment='基金经理编号')
    start_date = Column(db.DateTime)
    end_date = Column(db.DateTime)


class FundCompany(PkModel):
    """基金公司表
    """
    name = Column(db.String(30), comment='基金公司名称')
    co_id = Column(db.String(10), comment='基金公司编号')


class FundType(PkModel):
    __table_args__ = {'comment': '基金小类表'}

    name = Column(db.String(255))
    var_id = Column(db.Integer,
                    db.ForeignKey('fund_variety.id'),
                    comment='基金大类编号')


class FundVariety(PkModel):
    __table_args__ = {'comment': '基金大类表'}

    name = Column(db.String(255))


class InRule(PkModel):
    """这个问题比较复杂，需要后期再去设计"""
    start_quota = Column(db.Integer, comment='计费开始额度')
    end_quota = Column(db.Integer, comment='计费结束额度')


class Mgr(PkModel):
    __tablename__ = "mgrs"
    __table_args__ = {'comment': '基金经理'}

    mgr_id = Column(db.Integer, comment='经理编号（以天天基金为准）')
    name = Column(db.String(4), comment='经理名称')
    company_id = Column(db.Integer,
                        db.ForeignKey('fund_company.id'),
                        comment='所属公司ID')


class OutRule(PkModel):
    __table_args__ = {'comment': '赎回规则'}

    start_day = Column(db.Integer, comment='计费开始天数')
    end_day = Column(db.Integer, comment='计费结束天数')

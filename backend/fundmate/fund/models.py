#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Administrator at 2021/2/13 17:50

from backend.fundmate.database import Column, CreateDateModel, PkModel, CRUDMixin, db, reference_col, relationship


class DailyWorth(PkModel, CreateDateModel):
    """每日估算净值（真实净值按照基金名称分表存储）"""
    price = Column(db.Float, comment='基金单日净值')
    date = Column(db.Date, comment='日期')
    fund_id = reference_col('funds', column_kwargs={'comment': '基金编号'})
    fund = relationship("Fund", uselist=False, back_populates="daily_worth")


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
    '''
    基金、净值为一对一关系，所以需要对两者都添加`relationship`
    [Basic Relationship Patterns — SQLAlchemy 1.4 Documentation](https://docs.sqlalchemy.org/en/14/orm/basic_relationships.html#one-to-one)
    '''
    daily_worth = relationship('DailyWorth', back_populates='fund', uselist=False)


class FundRate(PkModel):
    fund_id = Column(db.Integer, db.ForeignKey('funds.id'), comment='基金编号')
    rule_id = Column(db.Integer, comment='费率编号')
    rate = Column(db.Integer, comment='费率百分比')
    type = Column(db.Boolean, nullable=True, comment='卖出或买入')  # TODO:多态关联


class FundMgr(PkModel):
    """relation between Fund and Mgr
    """
    __table_args__ = {'comment': '基金与经理关联表'}  # TODO: 关联表

    fund_id = Column(db.Integer, db.ForeignKey('funds.id'), comment='基金编号')
    mgr_id = Column(db.Integer, db.ForeignKey('mgrs.id'), comment='基金经理编号')
    start_date = Column(db.DateTime)
    end_date = Column(db.DateTime)


class FundCompany(PkModel, CRUDMixin):
    """基金公司表
    """
    code = Column(db.String(10), comment='基金公司编号')
    name = Column(db.String(30), comment='基金公司名称')
    create_date = Column(db.DateTime, comment='创建时间')
    scale = Column(db.Numeric(10, 2), nullable=True, comment='资产规模(亿元) ')  # 长度10，精度2
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
        server_default=db.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment='数据上次更新时间')

    @classmethod
    def is_exists(cls, f_code: str) -> bool:
        """
        根据code查询是否存在
        :param f_code:
        :return:
        """
        # https://stackoverflow.com/a/41951905
        return db.session.query(cls.query.filter(cls.code == f_code).exists()).scalar()

    def insert_or_update(self, f_code: str, **kwargs: dict):
        """
        创建或更新
        :param f_code:
        :param kwargs:
        :return:
        """
        is_comp_exists = self.is_exists(f_code)
        if is_comp_exists:
            ret = FundCompany.query.filter_by(code=f_code).update(kwargs)
            db.session.commit()
        else:
            ret = self.create(**kwargs)
        return ret


class FundType(PkModel):
    __table_args__ = {'comment': '基金小类表'}

    name = Column(db.String(255))
    var_id = Column(db.Integer,
                    db.ForeignKey('fund_variety.id'),
                    comment='基金大类编号')


class FundVariety(PkModel, CRUDMixin):
    __table_args__ = {'comment': '基金大类表'}

    name = Column(db.String(255))  # django model 中的 choices


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

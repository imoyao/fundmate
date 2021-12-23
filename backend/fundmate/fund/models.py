#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/2/13 17:50
from __future__ import annotations

import random
from decimal import Decimal
from typing import Optional, Union

from sqlalchemy import func, or_
from sqlalchemy.ext.hybrid import hybrid_property

from backend.fundmate import settings
from backend.fundmate.database import (
    ChoiceType,
    ChoiceTypeInteger,
    Column,
    CreateDateModel,
    PkModel,
    UpsertMixin,
    db,
    key2val,
    reference_col,
    relationship,
)


class DailyWorth(PkModel, CreateDateModel):
    """每日净值（初始净值数据按照基金名称分表存储，然后我们需要合并表）
    1. 考虑分表，主键应该使用uuid
    2. uuid vs GUID
    """
    price = Column(db.Float, comment='基金单日净值')
    date = Column(db.Date, comment='日期')
    fund_id = reference_col('funds', column_kwargs={'comment': '基金编号ID'})
    fund = relationship("Fund", uselist=False, back_populates="daily_worth")


class Fund(PkModel, UpsertMixin):
    """基金表"""
    __tablename__ = "funds"
    __table_args__ = {'comment': '基金表'}
    # TODO: 验证规则
    '''
    [《证券投资基金编码规范》实施细则](http://www.csisc.cn/zbscbzw/ywguize/201212/bf12c532a6c44cde864f59d9f2423f1b.shtml)
    [证券投资基金编码简介](http://www.csisc.cn/zbscbzw/cpbmjj/201212/f3263ab61f7c4dba8461ebbd9d0c6755.shtml)
    [证券投资基金编码规范](http://www.csisc.cn/zbscbzw/hyfbjcbmm/201904/d2587b8addb54335a87017af40344e24.shtml)
    [基金代码有什么规则？区分认购代码和交易代码 - 希财网](https://www.csai.cn/jijin/1298440.html)
    [基金代码含义及编制规则 - 知乎](https://zhuanlan.zhihu.com/p/24948157)
    '''
    fund_code = Column(db.String(6), unique=True, comment='基金编码')
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
    sxszm = Column('abbr_capital_initial_phonetic_alphabet', db.String(30), comment='缩写首字母拼音')
    qxpy = Column('full_capital_phonetic_alphabet', db.String(80), comment='全写拼音')
    f_type = Column('fund_type_id', db.Integer, db.ForeignKey('fund_type.id'), comment='基金小类编号')
    f_var = Column('fund_variety_id', db.Integer, db.ForeignKey('fund_variety.id'), comment='基金大类编号')
    co_id = Column(db.Integer, db.ForeignKey('fund_company.id'), comment='所属基金公司编号')
    create_time = Column(db.DateTime, comment='基金创建时间')
    symbol_prefix = Column(ChoiceType(choices=settings.SYMBOL_TYPE),
                           nullable=True,
                           default='UN',
                           comment='符号前缀（FP/SZ/SH）')
    risk_level = Column(ChoiceTypeInteger(choices=key2val(settings.RISK_TYPE)),
                        default=1,
                        nullable=True,
                        comment='风险等级')
    is_fe_charge_mode = Column(db.Boolean, comment='收费方式（前端/后端）')  #
    last_modified = Column(db.TIMESTAMP,
                           nullable=False,
                           server_default=db.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                           comment='数据上次更新时间')
    '''基金、净值为一对一关系，所以需要对两者都添加`relationship` [Basic Relationship Patterns — SQLAlchemy 1.4 Documentation](
    https://docs.sqlalchemy.org/en/14/orm/basic_relationships.html#one-to-one) '''
    daily_worth = relationship('DailyWorth', back_populates='fund', uselist=False)
    # 多对多
    mgrs = relationship('Mgr', secondary='fund_mgr', back_populates='funds')
    # 费率关系：一对多
    rate_rules = db.relationship('FeeRatio')

    @classmethod
    def search_key(cls, key):
        funds = cls.query.filter(
            or_(cls.name.ilike(f'%{key}%'), cls.fund_code.ilike(f'%{key}%'), cls.sxszm.ilike(f'%{key}%'),
                cls.qxpy.ilike(f'%{key}%'))).all()
        return funds

    @classmethod
    def code_by_name(cls, name: str) -> str:
        """根据基金名称获取基金编码"""
        code = cls.query.filter(cls.name.ilike(name)).all()
        return code

    @classmethod
    def filter_by_code(cls, code: str) -> Fund:
        """获取编码所对应的id
        """
        _ins = cls.query.filter_by(fund_code=code).first()
        return _ins

    def __repr__(self):
        return f"<Fund({self.fund_code!r}, {self.name!r})>"


class Mgr(PkModel, UpsertMixin):
    __tablename__ = "mgrs"
    __table_args__ = {'comment': '基金经理'}

    mgr_code = Column(db.Integer, comment='经理编号（以天天基金为准）')
    name = Column(db.String(30), comment='经理名称')  # 'FAN BING(范冰)' 带英文的字符长度
    company_id = Column(db.Integer, db.ForeignKey('fund_company.id'), comment='所属公司ID')
    work_days = Column(db.Integer, comment='总任职时间')  # TODO: 此处不需要写死，只记录上任日期即可，需要修改字段
    sum_scale = Column(db.Numeric(8, 2), nullable=True, comment='现管理资产总规模(亿元) ')  # 长度10，精度2
    best_rt = Column(db.Numeric(7, 2), nullable=True, comment='最佳回报(%) ')  # 长度10，精度2
    last_modified = Column(db.TIMESTAMP,
                           nullable=False,
                           server_default=db.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                           comment='数据上次更新时间')
    # 在管基金
    '''
    # **注意** secondary后面跟表名而不是类名
    sqlalchemy.exc.ArgumentError: secondary argument <class 'backend.fundmate.fund.models.FundMgr'> 
    passed to to relationship() Fund.mgrs must be a Table object or other FROM clause; 
    can't send a mapped class directly as rows in 'secondary' are persisted independently 
    of a class that is mapped to that same table.
    '''
    funds = relationship('Fund', secondary='fund_mgr', back_populates='mgrs')

    def __repr__(self):
        return f"<Fund Manager({self.mgr_code!r}, {self.name!r})>"

    @classmethod
    def filter_by_code(cls, code: str) -> Mgr:
        """获取编码所对应的id
        """
        _ins = cls.query.filter_by(mgr_code=code).first()
        return _ins

    @classmethod
    def present_funds(cls, mgr_code: str) -> Union[list, None]:
        """
        获取当前在管基金
        """
        _ins = cls.filter_by_code(mgr_code)
        if _ins:
            all_ever_managed_funds = _ins.funds

            all_now_managed_funds = list()
            for f in all_ever_managed_funds:
                fund_id = f.id
                f_inst = FundMgr.query.filter_by(fund_id=fund_id).first()
                if f_inst.end_date is None:
                    all_now_managed_funds.append(f)
            return all_now_managed_funds


class FundMgr(PkModel):
    """relation between Fund and Mgr
    注意：
    1. 基金经理与基金为 M2M
    ~~2. 此表只存现任关系，其他关系需要另一张表~~
    """
    __table_args__ = {'comment': '基金与经理关联表'}

    fund_id = Column(db.Integer, db.ForeignKey('funds.id'), comment='基金ID')
    mgr_id = Column(db.Integer, db.ForeignKey('mgrs.id'), comment='基金经理ID')
    is_classic = Column(db.Boolean, comment='是否属于该经理的代表作')
    start_date = Column(db.DateTime)
    end_date = Column(db.DateTime)


class FundCompany(PkModel, UpsertMixin):
    """基金公司表
    """
    code = Column(db.String(10), comment='基金公司编号')
    name = Column(db.String(30), comment='基金公司名称')
    create_date = Column(db.DateTime, comment='创建时间')
    scale = Column(db.Numeric(10, 2), nullable=True, comment='资产规模(亿元) ')  # 长度10，精度2
    dpy = Column('abbr_capital_initial_phonetic_alphabet', db.String(30), comment='缩写首字母拼音')
    tx_eval = Column(db.Integer, nullable=True, comment='天相评级（五星制）')
    full_name = Column(db.String(30), comment='基金公司全称')
    f_counts = Column(db.Integer, comment='拥有基金数量（参考值）')
    mgr = Column(db.String(10), comment='总经理')
    update_time = Column(db.DateTime, comment='数据更新时间')
    last_modified = Column(db.TIMESTAMP,
                           nullable=False,
                           server_default=db.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                           comment='数据上次更新时间')

    @classmethod
    def filter_by_code(cls, code: str) -> Union[int, None]:
        """获取编码所对应的id
        """
        _ins = cls.query.filter_by(code=code).first()
        if _ins:
            return _ins.id


class FundSaleOrg(PkModel, UpsertMixin):
    """基金销售机构
    在记账时，可以记录购买渠道
    """
    org_id = Column(db.Integer, comment='机构编号')
    name = Column(db.String(30), comment='机构名称')
    known_name = Column(db.String(10), comment='广为人知的代号')
    addr = Column(db.String(50), comment='注册地')
    org_type = Column(db.String(30), comment='机构类型')
    date = Column(db.String(10), comment='核准时间')

    def as_name(self):
        return self.known_name or self.name


class FundType(PkModel):
    """小类与基金为多对一，即：一个基金可以有多个小类"""
    __table_args__ = {'comment': '基金小类表'}

    name = Column(db.String(255), unique=True)
    var_id = Column(db.Integer, db.ForeignKey('fund_variety.id'), comment='基金大类编号')

    @classmethod
    def id_by_name(cls, name: str) -> Union[int, None]:
        """获取名称为指定分类的编号id
        """
        _ins = cls.query.filter_by(name=name).first()
        if _ins:
            return _ins.id


class FundVariety(PkModel, UpsertMixin):
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
    name = Column(db.String(255), unique=True)

    @classmethod
    def id_by_name(cls, name: str) -> Union[int, None]:
        """获取名称为指定分类的编号id
        """
        _ins = cls.query.filter_by(name=name).first()
        if _ins:
            return _ins.id


class InRule(PkModel, UpsertMixin):
    """
    可以直接记录结束点，然后每个出入都有3-4条记录，记录字段：分割点、费率、f_code
    """
    __table_args__ = {'comment': '申购/认购规则表'}

    start_quota = Column(db.Numeric(10, 2), comment='计费开始额度（金额：元）')  # max:10000000.00
    end_quota = Column(db.Numeric(10, 2), comment='计费结束额度（金额：元）')

    def readable_quota(self, quota: Union[int, float]) -> Union[str, int, float]:
        """
        将float类型配额转为可读字符
        Example:
        ```python
        In [2]: ir.readable_quota(0)
        Out[2]: 0

        In [3]: ir.readable_quota(100)
        Out[3]: 100

        In [4]: ir.readable_quota(10000)
        Out[4]: '1 万'

        In [5]: ir.readable_quota(50000000)
        Out[5]: '5000 万'

        In [6]: ir.readable_quota(float('inf'))
        Out[6]: inf
        ```
        :param quota:
        :return:
        """
        if quota is None:
            return float('inf')
        elif float('inf') > quota >= 10000:
            return f'{int(quota / 10000)} 万'
        else:
            return float(quota) if isinstance(quota, (float, Decimal)) else int(quota)

    def __repr__(self):
        return f"<InRule(start quota:{self.readable_quota(self.start_quota)!r}," \
               f"end quota:{self.readable_quota(self.end_quota)!r})> "


class OutRule(PkModel, UpsertMixin):
    __table_args__ = {'comment': '赎回规则表'}

    start_day = Column(db.Integer, comment='计费开始天数')
    end_day = Column(db.Integer, comment='计费结束天数')

    def __repr__(self):
        if self.end_day is None:
            self.end_day = float('inf')
        return f"<OutRule(start day:{self.start_day!r},end day:{self.end_day!r})>"


class FeeRatio(PkModel, UpsertMixin):
    """
    基金和费率表为O2M关系（一个基金有多个收费映射关系）
    费率和费率规则也是O2M关系（一个费率对应多个买入和卖出规则）
    """
    __table_args__ = {'comment': '费率记录表'}

    fund_id = Column(db.Integer, db.ForeignKey('funds.id'), comment='基金编号ID')
    in_rule_id = db.Column(db.Integer, db.ForeignKey('in_rule.id'), nullable=True, comment='申购规则ID')
    out_rule_id = db.Column(db.Integer, db.ForeignKey('out_rule.id'), nullable=True, comment='赎回规则ID')
    fee_type = Column(ChoiceTypeInteger(choices=key2val(settings.FEE_TYPE)),
                      nullable=True,
                      default=0,
                      comment='费率类型（认购、申购、赎回）')
    rate = Column(db.Numeric(3, 2), comment='费率百分比')
    fee_amount = Column(db.Numeric(6, 2), comment='收费金额（超过xx万时一次收费，此时rate应该为空）')
    last_modified = Column(db.TIMESTAMP,
                           nullable=False,
                           server_default=db.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                           comment='数据上次更新时间')

    def __repr__(self):
        f = Fund.get_by_id(self.fund_id)
        self.code = f.fund_code
        if self.fee_type in ['subscribe', 'purchase']:
            rule_class = InRule
        else:
            rule_class = OutRule
        rule_inst = rule_class.get_by_id(self.rule_id)
        return f"<FeeRatio(id:{self.fund_id},code:{self.code!r},type:{self.fee_type!r},{rule_inst!r})>"

    @hybrid_property
    def rule_id(self):
        """
        https://stackoverflow.com/a/60053408/14295718
        """
        return self.in_rule_id or self.out_rule_id

    @classmethod
    def get_rules(cls, fund_code: str, op_type: int):
        """
        获取基金对应的rule_id列表
        """
        f_id = Fund.filter_by_code(fund_code)
        rule_item_list = cls.query.filter_by(fund_id=f_id, fee_type=op_type).all()
        return rule_item_list

    @classmethod
    def buy_info(cls, fund_code: str, op_type: int = 1):
        """
        购买费率（包括申购和购买）
        """
        rule_item_list = cls.get_rules(fund_code, op_type)
        rules = list()
        for rule in rule_item_list:
            rule_id = rule.rule_id
            rule_rate = rule.rate
            rule_fee_amount = None
            if not rule_rate:
                rule_fee_amount = rule.fee_amount
            rule_inst = InRule.query.get_by_id(rule_id)
            if rule_inst:
                start_quota = rule_inst.start_quota
                end_quota = rule_inst.start_quota
                rule_info = {
                    'start_quota': start_quota,
                    'end_quota': end_quota,
                    'rate': rule_rate,
                    'rule_fee_amount': rule_fee_amount,
                }
                rules.append(rule_info)
        return rules

    @classmethod
    def redeem_info(cls, fund_code: str):
        """
        赎回费率
        """
        rule_item_list = cls.get_rules(fund_code, 3)
        rules = list()
        for rule in rule_item_list:
            rule_id = rule.rule_id
            rule_rate = rule.rate
            rule_fee_amount = None
            rule_inst = OutRule.query.get_by_id(rule_id)
            if rule_inst:
                start_day = rule_inst.start_day
                end_day = rule_inst.end_day
                if not rule_rate and end_day is float('inf'):
                    rule_fee_amount = 0
                rule_info = {
                    'start_day': start_day,
                    'end_day': end_day,
                    'rate': rule_rate,
                    'rule_fee_amount': rule_fee_amount,
                }
                rules.append(rule_info)
        return rules


def display(display_map: dict, pk_key: str) -> str:
    """
    数据库中存的是数字，保存是输入拼音，显示时应为可读信息
    :param pk_key:
    :param display_map:
    :return:
    """
    return display_map.get(pk_key)


class FundPortfolio(PkModel, CreateDateModel, UpsertMixin):
    """
    基金组合（回测、配置型）

    爬取一些具有代表性的组合并保存跟踪
    """
    __table_args__ = {'comment': '基金组合表'}

    portfolio_code = Column(db.String(10), comment='组合编码')  # 使用固定数字加随机数
    name = Column(db.String(30), comment='组合名称')
    code = Column(db.String(30), unique=True, comment='组合编码（各平台独有）')
    is_visible = Column(db.Boolean, comment='是否他人可见')  # 只有创建人（/admin）可以修改
    found_date = Column(db.Date, comment='组合创建日期')
    mgr_code = Column(db.String(10), comment='组合管理人编码')
    platform = Column(ChoiceTypeInteger(choices=key2val(settings.PLAT_TYPE)),
                      nullable=True,
                      default=0,
                      comment=f'平台名称：{str(settings.PLAT_TYPE_DISPLAY)}')
    risk_type = Column(ChoiceTypeInteger(choices=key2val(settings.RISK_TYPE)),
                       nullable=True,
                       default=0,
                       comment='风险类型（稳健/成长等）')
    annualized_rate_of_return = Column(db.Numeric(5, 2), comment='成立以来年化')  # 每天计算净值后更新
    invest_rate_of_return = Column(db.Numeric(5, 2), comment='成立以来收益')  # 每天计算净值后更新
    desc = Column(db.String(300), comment='组合描述')
    rich_desc = Column(db.String(1000), comment='组合详细描述')
    update_time = Column(db.DateTime, comment='组合更新时间')
    last_adjust_date = Column(db.Date, comment='组合最后一次调整时间')

    def __repr__(self):
        plat_name = display(settings.PLAT_TYPE_DISPLAY, self.platform)
        risk_name = display(settings.RISK_TYPE_DISPLAY, self.risk_type)
        return f"<FundPortfolio({self.name!r}, {plat_name!r}, {risk_name!r})>"

    @classmethod
    def gen_random_digit(cls) -> Optional[str]:
        """
        生成递增6位识别号
        :return:
        """
        fp_identifier = settings.INITIAL_PORTFOLIO_IDENTIFIER
        max_identifier = db.session.query(func.max(cls.portfolio_code)).one_or_none()
        if max_identifier != (None, ):
            max_num = max_identifier[0]
            if max_num is not None:
                increase_int = random.randrange(1, 3)
                fp_identifier = int(max_num) + increase_int
                return f'{fp_identifier:06}'
        return fp_identifier


class FundPortfolioMgr(PkModel, UpsertMixin):
    """
    组合管理人信息表
    需要注意的是：如果是自建组合，则管理人员信息应该从用户表查询
    """
    code = Column(db.String(10), unique=True, comment='组合管理人编码')  # 使用固定数字加随机数
    name = Column(db.String(30), comment='主理人')
    plat_code = Column(db.String(30), comment='组合管理人编号（各平台独有）')
    mgr_type = Column(ChoiceTypeInteger(choices=key2val(settings.ZH_MGR_TYPE)),
                      nullable=False,
                      default=0,
                      comment='组合管理人类型（1机构/0个人）')
    mgr_avatar_url = Column(db.String(300), comment='主理人头像链接')  # TODO:是否需要保存到本地
    platform = Column(ChoiceTypeInteger(choices=key2val(settings.PLAT_TYPE)),
                      nullable=True,
                      default=0,
                      comment=f'平台名称：{str(settings.PLAT_TYPE_DISPLAY)}')
    desc = Column(db.String(300), comment='组合管理人描述')

    def __repr__(self):
        plat_name = display(settings.PLAT_TYPE_DISPLAY, self.platform)
        return f"<FundPortfolioMgr({self.name!r}, {plat_name!r} )>"

    @classmethod
    def gen_mgr_code(cls) -> Optional[str]:
        """
        生成递增8+位识别号
        :return:
        """
        fp_identifier = settings.INITIAL_MGR_IDENTIFIER
        max_identifier = db.session.query(func.max(cls.code)).one_or_none()
        if max_identifier != (None, ):
            max_num = max_identifier[0]
            if max_num is not None:
                increase_int = random.randrange(1, 3)
                fp_identifier = int(max_num) + increase_int
                return f'{fp_identifier:08}'
        return fp_identifier


class FundPortfolioAdjustHistory(PkModel):
    """
    组合调仓历史
    """
    portfolio_code = Column(db.String(30), comment='组合编码')
    update_date = Column(db.DateTime, comment='调仓时间')
    adjust_id = Column(db.BigInteger, comment='调仓历史编码')  # 使用雪花算法
    plat_trade_id = Column(db.String(120), comment='平台调仓编码（只做记录区分用，不参与系统计算）')
    desc = Column(db.String(300), comment='调仓说明')

    def __repr__(self):
        return f"组合( {self.portfolio_code!r} ) 调仓时间： {self.update_date!r}，记录编号：{self.adjust_id!r}>"

    # def get_record_adjust_count(self, portfolio_code: str):
    #     return FundPortfolioAdjustHistory.query.filter_by(portfolio_code=portfolio_code).count()

    @classmethod
    def adjust_count(cls, portfolio_code: str):
        """
        获取某个基金的调仓次数
        see also: [mysql - Why is SQLAlchemy count() much slower than the raw query? - Stack Overflow](
        https://stackoverflow.com/questions/14754994/why-is-sqlalchemy-count-much-slower-than-the-raw-query) :param
        portfolio_code: :return:
        """
        return db.session.query(func.count(cls.id)).filter(cls.portfolio_code == portfolio_code).scalar()


class FundPortfolioHoldDetail(PkModel):
    """
    组合持仓明细
    {
        "trading_id": "281b3d8bad024b7ea2eeb37bfb7b8a5f",
        "fd_code": "161005",
        "fd_name": "富国天惠成长混合（LOF）A",
        "portion": 0.03,
        "money": 0,
        "last_portion": 0.0632,
        "volume": 0,
        "percent": "3.0%",
        "last_percent": "6.32%"
    }
    """
    fd_code = Column(db.String(6), comment='基金编码')
    adjust_id = Column(db.BigInteger, comment='调仓历史编码')
    portion = Column(db.Numeric(5, 4), comment='持仓占比，如：0.0716')

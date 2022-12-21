# -*- coding: utf-8 -*-
"""Application configuration.

Most configuration is set via environment variables.

For local development, use a .env file to set environment variables.
"""
import enum
from pathlib import Path

import pendulum
from environs import Env as EnvParser

from backend.fundmate.libs.dk_enums import BaseTypeEnum, ChoiceTypeDk, ChoiceTypeIntegerDk


env = EnvParser()
env.read_env()
ENV = env.str('FLASK_ENV', default='default')  # default is dev
"""
在开发环境下，调试模式（Debug Mode）将被开启，这时执行flask run 启动程序会自动激活 Werkzeug 内置的调试器（debugger）和重载器（reloader），它们会为开发带来很大的帮助。

如果你想单独控制调试模式的开关，可以通过FLASK_DEBUG环境变量设置，设为1则开启，设为0 则关闭，不过通常不推荐手动设置这个值。
"""
# SQLALCHEMY_DATABASE_URI = env.str('DATABASE_URL', '')  # 此处我们使用更小粒度控制
# SECRET_KEY = env.str('SECRET_KEY')
SEND_FILE_MAX_AGE_DEFAULT = env.int('SEND_FILE_MAX_AGE_DEFAULT', 43200)
BCRYPT_LOG_ROUNDS = env.int('BCRYPT_LOG_ROUNDS', default=13)
DEBUG_TB_INTERCEPT_REDIRECTS = False
CACHE_TYPE = 'simple'  # Can be 'memcached', 'redis', etc.
SQLALCHEMY_TRACK_MODIFICATIONS = False
CURRENT_DIR = Path(__file__).resolve().parent
INFO_MAIL_ADDR = 'fundmate@163.com'
"""
1998年3月23日，按该办法要求设立的开元、金泰两家封闭式证券投资基金公开发行上市，标志着我国证券市场新的机构投资者——证券投资基金的出现，我国的投资基金开始了封闭式证券投资基金时代。1998年我国共成立了第一批5只封闭式基金：基金开元、基金金泰、基金兴华、基金安信和基金裕阳。
2001年9月，经管理层批准，由华安基金管理公司成立了我国第一支开放式证券投资基金--华安创新，我国基金业的发展进入了一个崭新的阶段。

[新中国后,我国第一支股票和基金分别是什么时候发行的._百度知道](https://zhidao.baidu.com/question/215099298.html)
"""
INITIAL_PORTFOLIO_IDENTIFIER = '010921'
# 组合用户编号应该和组合编号有一定区分度：所以长度取长一点
INITIAL_MGR_IDENTIFIER = '20211202'
# 账户起始编号
INITIAL_ACCOUNT_IDENTIFIER = '1024'
# 理财产品起始编号
INITIAL_INVEST_PRODUCT_CODE_IDENTIFIER = '10000001'

UNDEFINED = ChoiceTypeIntegerDk(0, 'undefined', '未定义')
PLAIN = ChoiceTypeIntegerDk(1, 'plain', '灵活取用')
LOW = ChoiceTypeIntegerDk(2, 'low', '稳健增值')
BALANCE = ChoiceTypeIntegerDk(3, 'balance', '平衡增长')
ADVANCE = ChoiceTypeIntegerDk(4, 'advance', '进阶成长')
HIGH = ChoiceTypeIntegerDk(5, 'high', '积极进取')


class RiskTypeEnum(BaseTypeEnum):
    """风险等级"""
    undefined = UNDEFINED
    plain = PLAIN
    low = LOW
    balance = BALANCE
    advance = ADVANCE
    high = HIGH

    @classmethod
    def default(cls):
        """
        默认值，如果要使用非默认的默认值，则调用普通赋值操作即可
        :return:

        FIXME: py3.8+ [python - Using property() on classmethods - Stack Overflow](
        https://stackoverflow.com/questions/128573/using-property-on-classmethods)
        """
        return cls.balance

    @classmethod
    def input(cls):
        """
        用户请求时需要用到
        **注意：**只有当key为int时才有name属性
        :return:
        """
        return [item.dk_name for item in cls]


OP_PURCHASE = ChoiceTypeIntegerDk(1, 'purchase', '买入')
REDEEM = ChoiceTypeIntegerDk(2, 'redeem', '卖出')
TRANSFER = ChoiceTypeIntegerDk(3, 'transfer', '转换')
REGULAR_INVEST = ChoiceTypeIntegerDk(4, 'regular_invest', '定投')
CASH_BONUS = ChoiceTypeIntegerDk(5, 'cash_bonus', '现金分红')
ADJUST = ChoiceTypeIntegerDk(6, 'adjust', '调仓')
OTHER = ChoiceTypeIntegerDk(7, 'other', '其他')
TRANSFER_REFUND = ChoiceTypeIntegerDk(8, 'transfer_refund', '基金转换退款')
QUOT_BONUS = ChoiceTypeIntegerDk(9, 'quot_bonus', '份额分红')
DEPOSIT = ChoiceTypeIntegerDk(10, 'deposit', '存入')  # 从银行卡存入
DRAW_OUT = ChoiceTypeIntegerDk(11, 'draw_out', '取出')  # 取出到银行卡
REVOKE = ChoiceTypeIntegerDk(12, 'revoke', '撤销操作')  # 取出到银行卡


# 风险等级
@enum.unique
class FundOpTypeEnum(BaseTypeEnum):
    """
    操作分类
    """
    purchase = OP_PURCHASE
    redeem = REDEEM
    transfer = TRANSFER
    regular_invest = REGULAR_INVEST
    cash_bonus = CASH_BONUS
    adjust = ADJUST
    other = OTHER
    transfer_refund = TRANSFER_REFUND
    quot_bonus = QUOT_BONUS
    deposit = DEPOSIT
    draw_out = DRAW_OUT
    revoke = REVOKE

    @classmethod
    def default(cls):
        return cls.purchase

    @classmethod
    def input(cls):
        """
        :return:
        """
        return [item.dk_name for item in cls]

    @classmethod
    def display(cls):
        """
        显示汉字内容
        :return:
        """
        return [item.dk_display for item in cls]

    @classmethod
    def columns_map(cls) -> dict:
        """
        返回英文和中文的映射字典
        :return:
        """
        input_li = cls.input()
        display_li = cls.display()
        return dict(zip(input_li, display_li))


UNSE = ChoiceTypeDk('UN', '未知')
FPSE = ChoiceTypeDk('FP', '暂时未知交易所')
SZSE = ChoiceTypeDk('SZ', '深圳证券交易所')
SHSE = ChoiceTypeDk('SH', '上海证券交易所')
SEHK = ChoiceTypeDk('HK', '香港证券交易所')


@enum.unique
class SymbolTypeEnum(BaseTypeEnum):
    """
    基金决策宝的symbol的前缀，UN表示未知
    """
    UN = UNSE
    FP = FPSE
    SZ = SZSE
    SH = SHSE
    HK = SEHK

    @classmethod
    def default(cls):
        return cls.UN

    @classmethod
    def input(cls):
        """
        用户请求时需要用到
        :return:
        """
        return [item.dk_value for item in cls]


UNKNOWN = ChoiceTypeIntegerDk(0, 'unknown', '未定义')
SUBSCRIBE = ChoiceTypeIntegerDk(1, 'subscribe', '基金认购')
PURCHASE = ChoiceTypeIntegerDk(2, 'purchase', '基金申购')
REDEEM_FEE = ChoiceTypeIntegerDk(3, 'redeem', '基金赎回')


@enum.unique
class FeeTypeEnum(BaseTypeEnum):
    """
    费率类型
    """
    unknown = UNKNOWN
    subscribe = SUBSCRIBE
    purchase = PURCHASE
    redeem = REDEEM_FEE

    @classmethod
    def default(cls):
        return cls.unknown


ZH_PERSONAL = ChoiceTypeIntegerDk(0, 'personal', '个人')
ZH_ORG = ChoiceTypeIntegerDk(1, 'org', '机构')


@enum.unique
class ZHMgrTypeEnum(BaseTypeEnum):
    """
    组合管理人类型
    """
    personal = ZH_PERSONAL
    org = ZH_ORG

    @classmethod
    def default(cls):
        return cls.personal

    @classmethod
    def input(cls):
        """
        用户请求时需要用到
        :return:
        """
        return [item.dk_name for item in cls]


UNDEFINED_PLT = ChoiceTypeIntegerDk(0, 'un', '未定义')
QIEMAN = ChoiceTypeIntegerDk(1, 'qm', '且慢')
TIANTIAN = ChoiceTypeIntegerDk(2, 'tt', '天天基金')
DANJUAN = ChoiceTypeIntegerDk(3, 'dj', '蛋卷基金')
OWN = ChoiceTypeIntegerDk(4, 'own', '平台自建')
HOWBUY = ChoiceTypeIntegerDk(5, 'hb', '好买基金')


@enum.unique
class PlatTypeEnum(BaseTypeEnum):
    un = UNDEFINED_PLT
    qm = QIEMAN
    tt = TIANTIAN
    dj = DANJUAN
    own = OWN
    hb = HOWBUY

    @classmethod
    def default(cls):
        return cls.un

    @classmethod
    def input(cls):
        """
        用户请求时需要用到
        :return:
        """
        return [item.dk_name for item in cls]


UNPLT = ChoiceTypeDk('unknown', '未知平台')
ALIPAY = ChoiceTypeDk('alipay', '蚂蚁财富（支付宝）')
TCWM = ChoiceTypeDk('tcwm', '腾讯理财通')
TTJJ = ChoiceTypeDk('tt', '天天基金')


@enum.unique
class SupportInvestPltEnum(BaseTypeEnum):
    """
    支持导入文件的平台
    """
    unknown = UNPLT
    alipay = ALIPAY
    tcwm = TCWM
    tt = TTJJ

    @classmethod
    def input(cls):
        """
        用户请求时需要用到
        :return:
        """
        return [item.dk_value for item in cls]


"""
CNY（Chinese Yuan）人民币

FRF（French Franc）法国法郎

HKD（Hong Kong Dollar）港元

CHF（ Schweizer Franc）瑞士法郎

USD（United States Dollar）美元

CAD（Canadian Dollar）加拿大元

GBP（Great Britain Pound）英镑

NLG（Netherlandish Guilder）荷兰盾

DEM（Deutsche M ark）德国马克

BEF（Belgischer Franc）比利时法郎

JPY（Japanese Yen）日元

AUD（Australian Dollar）澳大利亚元

RUB（Russian Ruble）俄罗斯卢布

PHP（Philippine Peso）菲律宾比索

ITL （Italian Lira） 意大利里拉

"""
CNY = ChoiceTypeDk('CNY', '人民币')
FRF = ChoiceTypeDk('FRF', '法国法郎')
HKD = ChoiceTypeDk('HKD', '港元')
CHF = ChoiceTypeDk('CHF', '瑞士法郎')
USD = ChoiceTypeDk('USD', '美元')
CAD = ChoiceTypeDk('CAD', '加拿大元')
GBP = ChoiceTypeDk('GBP', '英镑')
NLG = ChoiceTypeDk('NLG', '荷兰盾')
DEM = ChoiceTypeDk('DEM', '德国马克')
BEF = ChoiceTypeDk('BEF', '比利时法郎')
JPY = ChoiceTypeDk('JPY', '日元')
AUD = ChoiceTypeDk('AUD', '澳大利亚元')
RUB = ChoiceTypeDk('RUB', '俄罗斯卢布')
PHP = ChoiceTypeDk('PHP', '菲律宾比索')
ITL = ChoiceTypeDk('ITL', '意大利里拉')


@enum.unique
class SupportCurrencyEnum(BaseTypeEnum):
    """
    支持导入文件的平台
    """
    CNY = CNY
    FRF = FRF
    HKD = HKD
    CHF = CHF
    USD = USD
    CAD = CAD
    GBP = GBP
    NLG = NLG
    DEM = DEM
    BEF = BEF
    JPY = JPY
    AUD = AUD
    RUB = RUB
    PHP = PHP
    ITL = ITL


FUND = ChoiceTypeDk('fund', '基金')
STOCK = ChoiceTypeDk('stock', '股票')
BOND = ChoiceTypeDk('bond', '可转债')
FUTURES = ChoiceTypeDk('futures', '期货')
PORTFOLIO = ChoiceTypeDk('portfolio', '投顾组合')
FINANCIAL_PRODUCT = ChoiceTypeDk('fina_product', '理财产品')


@enum.unique
class SupportInvestCategoriesEnum(BaseTypeEnum):
    """
    支持的交易品类
    """
    fund = FUND
    stock = STOCK
    bond = BOND
    futures = FUTURES
    portfolio = PORTFOLIO
    financial_product = FINANCIAL_PRODUCT

    @classmethod
    def input(cls):
        """
        用户请求时需要用到
        :return:
        """
        return [item.dk_value for item in cls]


MANAGERS = ChoiceTypeDk('managers', '基金经理')
INDEX = ChoiceTypeDk('index', '指数')


@enum.unique
class SupportCollectionsEnum(BaseTypeEnum):
    """
    支持自选的类别
    """
    fund = FUND
    stock = STOCK
    bond = BOND
    futures = FUTURES
    portfolio = PORTFOLIO
    financial_product = FINANCIAL_PRODUCT
    managers = MANAGERS
    index = INDEX

    @classmethod
    def input(cls) -> list:
        """
        用户请求时需要用到
        :return:
        """
        return [item.dk_value for item in cls]


# 正则
"""
- at least 6 characters
- must contain at least 1 letter, and 1 number
- Can contain special characters
"""
PASSWORD_REG = r'^(?=.*\d)(?=.*[a-z])(?=.*[a-zA-Z]).{6,}$'
"""flask-praetorian 相关配置项"""

SITE_NAME = env.str('SITE_NAME', default='你的网站名称')

DEFAULT_JWT_ACCESS_LIFESPAN = pendulum.duration(hours=24)
DEFAULT_JWT_REFRESH_LIFESPAN = pendulum.duration(days=30)
DEFAULT_JWT_RESET_LIFESPAN = pendulum.duration(minutes=10)

# DEFAULT_CONFIRMATION_TEMPLATE = ("{}/authentication/templates/registration_email.html".format(
#     dirname(dirname(abspath(__file__))), ))

DEFAULT_CONFIRMATION_SENDER = env.str('MAIL_USERNAME')
DEFAULT_CONFIRMATION_SUBJECT = f'请激活你的{SITE_NAME}帐号'

# DEFAULT_RESET_TEMPLATE = ("{}/authentication/templates/reset_email.html".format(dirname(dirname(abspath(
# __file__))), ))
DEFAULT_RESET_SUBJECT = f'您在 {SITE_NAME} 发起重置密码请求'

DEFAULT_CONFIRMATION_URI = 'http://localhost:5000/register-confirm'
DEFAULT_RESET_URI = 'http://localhost:5000/reset-password'

ADMIN_ROLE_NAME = 'admin'
"""
# 好买
年化收益率代表期间内收益率的年化值。注：区间小于1年不展示年化收益率；

年化波动率代表产品过去的波动幅度，指标越小越好，指标越大则风险也越高；

夏普比率指区间内的年化夏普比率，代表每承担一份风险，可带来多少超额收益，该值越高说明产品的性价比越高；

最大回撤代表期间组合净值从最高到最低的下降幅度，指标越小越好。
"""
# 来自蛋卷组合详情信息返回值
INDICATOR_DOCS = [{
    'type': 'yield',
    'title': '年化收益率',
    'docs': ['组合内成分基金的累计收益率，代表了每只成分基金在组合中截至目前的收益率情况']
}, {
    'type':
        'max_drawdown',
    'title':
        '最大回撤',
    'docs': [
        '组合成立以来，净值走到最低点时的收益率回撤幅度的最大值。',
        ' 最大回撤用来描述买入产品后可能出现的最糟糕的情况。通常用来衡量该组合的抗风险能力。',
        '计算组合成立以来时间的回撤，基准指数的时间范围与组合一致。',
        '指标越小越好'
    ]
}, {
    'type': 'votility',
    'title': '年化波动率',
    'docs': ['代表组合资产收益率的年化波动 程度。通常用来衡量该组合的风险水平。',
             '以近一年的周涨跌计算年化波动率，若组合成立时间不足半年，不具备参考价值，不展示该数据。', '指标越小越好']
}, {
    'type':
        'sharpe',
    'title':
        '夏普比率',
    'docs': [
        '代表每承受一单位总风险，会产生多少的超额报酬。',
        ' 如果夏普比率为正值，说明在近一年组合平均收益率超过了无风险利率。',
        '以近一年的组合数据计算夏普，若组合成立时间不足半年，不具备参考价值，不展示该数据。',
        '该值越高说明产品的性价比越高'
    ]
}, {
    'type': 'annual_returns',
    'title': '年化收益率',
    'docs': [' 采用XIRR算法计算组合年化收益率。']
}, {
    'type': 'total_gain_rate',
    'title': '组合收益率',
    'docs': ['组合截至最新日期的累计收益率；收益率=组合累计收益/最大净流入成本。']
}, {
    'type': 'position',
    'title': '持仓分布',
    'docs': ['按照当前组合持仓的成分基金 的持仓比例、类型等，统计得到组合当前持仓分布']
}, {
    'type': 'purchase_time',
    'title': '买入次数',
    'docs': ['从组合创建开始，发布买入的方案中买入对应成分基金的次数']
}, {
    'type': 'hold_days',
    'title': '持有天数',
    'docs': ['从组合创建开始，对应成分基金总计的持有天数']
}, {
    'type': 'total_benefit_rate',
    'title': '累计收益率',
    'docs': ['组合内成分基金的累计收益率，代表了每只成分 基金在组合中截至目前的收益率情况']
}]

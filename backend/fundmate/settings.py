# -*- coding: utf-8 -*-
"""Application configuration.

Most configuration is set via environment variables.

For local development, use a .env file to set environment variables.
"""
import enum
from pathlib import Path
from types import DynamicClassAttribute

import pendulum
from environs import Env as EnvParser

from backend.fundmate.libs.dataklasses import dataklass

env = EnvParser()
env.read_env()
ENV = env.str("FLASK_ENV", default="default")  # default is dev
'''
在开发环境下，调试模式（Debug Mode）将被开启，这时执行flask run 启动程序会自动激活 Werkzeug 内置的调试器（debugger）和重载器（reloader），它们会为开发带来很大的帮助。

如果你想单独控制调试模式的开关，可以通过FLASK_DEBUG环境变量设置，设为1则开启，设为0 则关闭，不过通常不推荐手动设置这个值。
'''
DEBUG = ENV == "development"
SQLALCHEMY_DATABASE_URI = env.str("DATABASE_URL", '')  # 此处我们使用更小粒度控制
# SECRET_KEY = env.str("SECRET_KEY")
SEND_FILE_MAX_AGE_DEFAULT = env.int("SEND_FILE_MAX_AGE_DEFAULT", 43200)
BCRYPT_LOG_ROUNDS = env.int("BCRYPT_LOG_ROUNDS", default=13)
DEBUG_TB_ENABLED = DEBUG
DEBUG_TB_INTERCEPT_REDIRECTS = False
CACHE_TYPE = "simple"  # Can be "memcached", "redis", etc.
SQLALCHEMY_TRACK_MODIFICATIONS = False
CURRENT_DIR = Path(__file__).resolve().parent
INFO_MAIL_ADDR = 'fundmate@163.com'
'''
1998年3月23日，按该办法要求设立的开元、金泰两家封闭式证券投资基金公开发行上市，标志着我国证券市场新的机构投资者——证券投资基金的出现，我国的投资基金开始了封闭式证券投资基金时代。1998年我国共成立了第一批5只封闭式基金：基金开元、基金金泰、基金兴华、基金安信和基金裕阳。
2001年9月，经管理层批准，由华安基金管理公司成立了我国第一支开放式证券投资基金--华安创新，我国基金业的发展进入了一个崭新的阶段。

[新中国后,我国第一支股票和基金分别是什么时候发行的._百度知道](https://zhidao.baidu.com/question/215099298.html)
'''
INITIAL_PORTFOLIO_IDENTIFIER = '010921'
# 组合用户编号应该和组合编号有一定区分度：所以长度取长一点
INITIAL_MGR_IDENTIFIER = '20211202'
# 账户起始编号
INITIAL_ACCOUNT_IDENTIFIER = '1024'

# 风险等级
RISK_TYPE = {
    'undefined': 0,  # 未定义
    'plain': 1,  # 灵活取用
    'low': 2,  # 稳健增值
    'balance': 3,  # 平衡增长
    'advance': 4,  # 进阶成长
    'high': 5,  # 积极进取
}
RISK_TYPE_DISPLAY = {
    'undefined': '未定义',
    'plain': '灵活取用',
    'low': '稳健增值',
    'balance': '平衡增长',
    'advance': '进阶成长',
    'high': '积极进取'
}
# 基金决策宝的symbol的前缀,UN表示未知
SYMBOL_TYPE = {'UN': 0, 'FP': 1, 'SZ': 2, 'SH': 3}

# 费率类型
FEE_TYPE = {
    'unknown': 0,  # 未定义
    'subscribe': 1,  # 基金认购
    'purchase': 2,  # 基金申购
    'redeem': 3,  # 基金赎回
}

#  组合管理人类型
ZH_MGR_TYPE = {
    'personal': 0,  # '个人'
    'org': 1,  # '机构'
}
ZH_MGR_TYPE_DISPLAY = {
    'personal': '个人',
    'org': '机构',
}
PLAT_TYPE = {
    'undefined': 0,  # '未定义'
    'qm': 1,  # '且慢'
    'tt': 2,  # '天天基金'
    'dj': 3,  # '蛋卷基金'
    'own': 4,
    'hb': 5,
}

PLAT_TYPE_DISPLAY = {
    'undefined': '未定义',
    'qm': '且慢',
    'tt': '天天基金',
    'dj': '蛋卷基金',
    'own': '平台自建',
    'hb': '好买基金',
}


@dataklass
class ChoiceTypeIntegerDk:
    value: int
    name: str
    label: str

    @property
    def display(self):
        return self.label


@dataklass
class ChoiceTypeDk:
    value: str
    label: str

    @property
    def display(self):
        return self.label


@enum.unique
class BaseTypeEnum(enum.Enum):

    def __str__(self):
        return 'My custom dataklass {0}'.format(self.value)

    @DynamicClassAttribute
    def dk_name(self):
        """The name of the Enum member."""
        return self._value_.name

    @DynamicClassAttribute
    def dk_value(self):
        """The value of the Enum member."""
        return self._value_.value

    @DynamicClassAttribute
    def dk_display(self):
        """The value of the Enum member."""
        return self._value_.label

    def describe(self):
        # self is the member here
        return self.name, self.value

    @classmethod
    def comment(cls) -> str:
        enum_explains = dict()
        for name, member in cls.__members__.items():
            key = member.dk_value
            enum_explains[key] = member.dk_display
        return str(enum_explains)


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
        cls here is the enumeration
        FIXME: py3.8+ [python - Using property() on classmethods - Stack Overflow](https://stackoverflow.com/questions/128573/using-property-on-classmethods)
        :return:
        """
        return cls.balance


OP_PURCHASE = ChoiceTypeIntegerDk(1, 'purchase', '买入/存入/申购')
SALE = ChoiceTypeIntegerDk(2, 'sale', '赎回/卖出/支取')
TRANSFER = ChoiceTypeIntegerDk(3, 'transfer', '转换/转存')
REGULAR_INVEST = ChoiceTypeIntegerDk(4, 'regular_invest', '定投')
BONUS = ChoiceTypeIntegerDk(5, 'bonus', '分红')
ADJUST = ChoiceTypeIntegerDk(6, 'adjust', '调仓')
OTHER = ChoiceTypeIntegerDk(7, 'other', '其他')


# 风险等级
@enum.unique
class FundOpTypeEnum(BaseTypeEnum):
    """
    操作分类
    """
    purchase = OP_PURCHASE
    sale = SALE
    transfer = TRANSFER
    regular_invest = REGULAR_INVEST
    bonus = BONUS
    adjust = ADJUST
    other = OTHER

    @classmethod
    def default(cls):
        return cls.purchase


UNSE = ChoiceTypeDk('UN', '未知')
FPSE = ChoiceTypeDk('FP', '暂时未知交易所')
SZSE = ChoiceTypeDk('SZ', '深圳证券交易所')
SHSE = ChoiceTypeDk('SH', '上海证券交易所')
SEHK = ChoiceTypeDk('HK', '香港证券交易所')


@enum.unique
class SymbolTypeEnum(BaseTypeEnum):
    UN = UNSE
    FP = FPSE
    SZ = SZSE
    SH = SHSE
    HK = SEHK

    @classmethod
    def default(cls):
        return cls.UN


UNKNOWN = ChoiceTypeIntegerDk(0, 'unknown', '未定义')
SUBSCRIBE = ChoiceTypeIntegerDk(1, 'subscribe', '基金认购')
PURCHASE = ChoiceTypeIntegerDk(2, 'purchase', '基金申购')
REDEEM = ChoiceTypeIntegerDk(3, 'redeem', '基金赎回')


@enum.unique
class FeeTypeEnum(BaseTypeEnum):
    """
    费率类型
    """
    unknown = UNKNOWN
    subscribe = SUBSCRIBE
    purchase = PURCHASE
    redeem = REDEEM

    @classmethod
    def default(cls):
        return cls.unknown


ZH_PERSONAL = ChoiceTypeIntegerDk(0, 'personal', '个人')
ZH_ORG = ChoiceTypeIntegerDk(1, 'org', '机构')


@enum.unique
class ZHMgrTypeEnum(BaseTypeEnum):
    personal = ZH_PERSONAL
    org = ZH_ORG

    @classmethod
    def default(cls):
        return cls.personal


UN = ChoiceTypeIntegerDk(0, 'un', '未定义')
QM = ChoiceTypeIntegerDk(1, 'qm', '且慢')
TT = ChoiceTypeIntegerDk(2, 'tt', '天天基金')
DJ = ChoiceTypeIntegerDk(3, 'dj', '蛋卷基金')
OWN = ChoiceTypeIntegerDk(4, 'own', '平台自建')
HB = ChoiceTypeIntegerDk(5, 'hb', '好买基金')


@enum.unique
class PlatTypeEnum(BaseTypeEnum):
    undefined = UN
    qieman = QM
    tiantian = TT
    danjuan = DJ
    own = OWN
    howbuy = HB

    @classmethod
    def default(cls):
        return cls.undefined


# 正则
'''
- at least 6 characters
- must contain at least 1 letter, and 1 number
- Can contain special characters
'''
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

# DEFAULT_RESET_TEMPLATE = ("{}/authentication/templates/reset_email.html".format(dirname(dirname(abspath(__file__))), ))
DEFAULT_RESET_SUBJECT = f'您在 {SITE_NAME} 发起重置密码请求'

DEFAULT_CONFIRMATION_URI = 'http://localhost:5000/register-confirm'
DEFAULT_RESET_URI = 'http://localhost:5000/reset-password'

ADMIN_ROLE_NAME = 'admin'

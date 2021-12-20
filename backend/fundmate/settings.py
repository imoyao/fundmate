# -*- coding: utf-8 -*-
"""Application configuration.

Most configuration is set via environment variables.

For local development, use a .env file to set environment variables.
"""
from pathlib import Path

from environs import Env as EnvParser

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
SEND_FILE_MAX_AGE_DEFAULT = env.int("SEND_FILE_MAX_AGE_DEFAULT")
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

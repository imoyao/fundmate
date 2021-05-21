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
SECRET_KEY = env.str("SECRET_KEY")
SEND_FILE_MAX_AGE_DEFAULT = env.int("SEND_FILE_MAX_AGE_DEFAULT")
BCRYPT_LOG_ROUNDS = env.int("BCRYPT_LOG_ROUNDS", default=13)
DEBUG_TB_ENABLED = DEBUG
DEBUG_TB_INTERCEPT_REDIRECTS = False
CACHE_TYPE = "simple"  # Can be "memcached", "redis", etc.
SQLALCHEMY_TRACK_MODIFICATIONS = False
CURRENT_DIR = Path(__file__).resolve().parent
INFO_MAIL_ADDR = 'fundmate@163.com'

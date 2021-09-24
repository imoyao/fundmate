#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
用于flask相关的配置
http://www.pythondoc.com/flask/config.html#id6
"""
from pathlib import Path

from backend.fundmate import settings

env = settings.env

CURRENT_DIR = Path(__file__).resolve().parent


class Config:
    DEBUG = False
    TESTING = False
    CSRF_ENABLED = True
    SECRET_KEY = env.str('SECRET_KEY', default='MPk2WlUArcLeeU_iohzT')
    '''
    # 旧版本
    import random
    import string
    ''.join(random.choices(string.ascii_letters + string.digits, k=15))
    # py3.6+
    import secrets
    secrets.token_urlsafe(nbytes=15)
    '''
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = True
    # 分页
    POSTS_PER_PAGE = 10
    # 上传图片路径
    UPLOADED_IMAGES_DEST = Path(CURRENT_DIR).joinpath('static/images')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    # 邮件服务器设置
    MAIL_SERVER = env.str('MAIL_SERVER', default='smtp.163.com')
    # 163不支持STARTTLS
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    MAIL_USERNAME = env.str('MAIL_USERNAME')
    MAIL_PASSWORD = env.str('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = ('基小伴', env.str('MAIL_USERNAME'))
    # redis 配置
    # REDIS_URL = 'redis://:password@localhost:6379/0'
    REDIS_URL = env.str('REDIS_PATH', default='redis://localhost:6379/0')

    # openAPI
    SPEC_FORMAT = env.str('SPEC_FORMAT', 'json')
    LOCAL_SPEC_PATH = env.str('LOCAL_SPEC_PATH', 'openapi.json')
    LOCAL_SPEC_JSON_INDENT = env.int('LOCAL_SPEC_JSON_INDENT', 4)
    SYNC_LOCAL_SPEC = env.bool('SYNC_LOCAL_SPEC', True)

    def __init__(self):
        pass

    @staticmethod
    def init_app(app):
        pass


class MySQLConfig:
    MYSQL_USERNAME = env.str('MYSQL_USER')
    MYSQL_PASSWORD = env.str('MYSQL_PASSWORD')  # TODO: 环境变量获取失败
    MYSQL_DB = env.str('MYSQL_DB', '')
    MYSQL_HOST = env.str('MYSQL_HOST', 'localhost')
    MYSQL_PORT = env.int('MYSQL_PORT', 3306)
    MYSQL_ADDR = f'{MYSQL_HOST}:{MYSQL_PORT}'
    MYSQL_CHARSET = 'utf8mb4'  # 为了支持 emoji 显示，需要设置为 utf8mb4 编码
    MYSQL_DIALECT = 'mysql'  # 使用的数据库
    MYSQL_DRIVER = 'pymysql'  # 指定引擎


def mysql_url(db):
    sql_url = f'{MySQLConfig.MYSQL_DIALECT}+{MySQLConfig.MYSQL_DRIVER}://{MySQLConfig.MYSQL_USERNAME}:' \
              f'{MySQLConfig.MYSQL_PASSWORD}@{MySQLConfig.MYSQL_ADDR}/{db}?charset={MySQLConfig.MYSQL_CHARSET}'
    return sql_url


# TODO: 使用的数据库有待更改
class DevelopmentConfig(Config):
    DEBUG = settings.DEBUG
    DATABASE = MySQLConfig.MYSQL_DB or 'fmp_dev'
    SQLALCHEMY_DATABASE_URI = mysql_url(DATABASE)


class TestingConfig(Config):
    TESTING = True
    DATABASE = MySQLConfig.MYSQL_DB or 'fmp_test'
    SQLALCHEMY_DATABASE_URI = mysql_url(DATABASE)


class ProductionConfig(Config):
    DATABASE = MySQLConfig.MYSQL_DB or 'fmp_product'
    SQLALCHEMY_DATABASE_URI = mysql_url(DATABASE)


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

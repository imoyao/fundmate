import enum
from os.path import abspath, dirname

import pendulum

from backend.fundmate.settings import env
"""
flask-praetorian 配置 see also: https://github.com/J999Ventura/prj36_38834_38950_dblocks/blob/c63c4d5d5a48449a13fc5fed9314108ea7185820/03_Implementacao/Docker/server/src/api/v1/authentication/constants.py
"""
SITE_NAME = env.str('SITE_NAME', default='你的网站名称')

DEFAULT_JWT_HEADER_NAME = 'Authorization'
DEFAULT_JWT_HEADER_TYPE = 'Bearer'
DEFAULT_JWT_ACCESS_LIFESPAN = pendulum.duration(minutes=15)
DEFAULT_JWT_REFRESH_LIFESPAN = pendulum.duration(days=30)
DEFAULT_JWT_RESET_LIFESPAN = pendulum.duration(minutes=10)
DEFAULT_JWT_ALGORITHM = 'HS256'
DEFAULT_JWT_ALLOWED_ALGORITHMS = ['HS256']

DEFAULT_CONFIRMATION_TEMPLATE = ("{}/authentication/templates/registration_email.html".format(
    dirname(dirname(abspath(__file__))), ))

DEFAULT_CONFIRMATION_SENDER = env.str('MAIL_USERNAME')
DEFAULT_CONFIRMATION_SUBJECT = f'请激活你的{SITE_NAME}帐号'

DEFAULT_RESET_TEMPLATE = ("{}/authentication/templates/reset_email.html".format(dirname(dirname(abspath(__file__))), ))
DEFAULT_RESET_SUBJECT = f'您在 {SITE_NAME} 发起重置密码请求'

DEFAULT_CONFIRMATION_URI = 'http://localhost:5000/register-confirm'
DEFAULT_RESET_URI = 'http://localhost:5000/reset-password'

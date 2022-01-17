# -*- coding: utf-8 -*-
"""flask-praetorian 相关配置项"""
import pendulum

from backend.fundmate.settings import env

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

# -*- coding: utf-8 -*-
"""The app module, containing the app factory function."""
import logging
import sys

from apiflask import APIFlask
from flask import Flask

from backend.fundmate import account, commands, fund, public, settings, user
from backend.fundmate.config import config
from backend.fundmate.extensions import bcrypt, db, login_manager, loguru, migrate
from backend.fundmate.settings import env

from .exts.flask_loguru import logger


def create_app(config_object: str = "backend.fundmate.settings"):
    """Create application factory, as explained here: https://flask.pocoo.org/docs/patterns/appfactories/.

    :param config_object: The configuration object to use.
    """
    # see also:[APIFlask](https://apiflask.com/#example)
    app = APIFlask(__name__, title='基伴 API', version='1.0.0')
    app.config.from_object(config_object)
    update_config(app)
    register_extensions(app)
    register_blueprints(app)
    register_error_handlers(app)
    register_shell_context(app)
    register_commands(app)
    configure_logger(app)
    logger.info('Flask app has created!')
    '''
    RuntimeError: No application found. Either work inside a view function or push an application context. 
    See http://flask-sqlalchemy.pocoo.org/contexts/ .
    see also: https://blog.csdn.net/zhongqiushen/article/details/79162792
    '''
    app.app_context().push()
    return app


def register_extensions(app: Flask):
    """Register Flask extensions."""
    bcrypt.init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    '''
    - 增加字段长度和类型检测 
    [No changes detected in Alembic autogeneration of migrations with Flask-SQLAlchemy - Stack
    Overflow]( https://stackoverflow.com/questions/12409724/no-changes-detected-in-alembic-autogeneration-of
    -migrations-with -flask-sqlalchem)
    [[AF] Flask migrate does not recognise a change made in my post model. :flask]
    (https://www.reddit.com/r/flask/comments/98kmhe/af_flask_migrate_does_not_recognise_a_change_made/)
    - 新更新内容无法探测 
    [python - Flask-Migrate No Changes Detected to Schema on first migration - Stack Overflow](https://stackoverflow.com/questions/51783300/flask-migrate-no-changes-detected-to-schema-on-first-migration)
    [python - flask-migrate doesn't detect models - Stack Overflow](https://stackoverflow.com/questions/26564784/flask-migrate-doesnt-detect-models)
    '''  # noqa:E501
    migrate.init_app(app, db, compare_type=True)
    loguru.init_app(app, {
        "LOG_PATH": env.str('LOG_PATH', default='/home/work/var/log'),
        "LOG_NAME": env.str('LOG_NAME', default='app.log'),
    })
    return None


def register_blueprints(app: Flask):
    """Register Flask blueprints."""
    app.register_blueprint(public.views.bp)
    app.register_blueprint(user.views.bp)
    app.register_blueprint(fund.views.bp)
    return None


def register_error_handlers(app: Flask):
    """Register error handlers."""

    def render_error(error):
        """Render error template."""
        # If a HTTPException, pull the `code` attribute; default to 500
        error_code = getattr(error, "code", 500)
        logger.info(error_code)
        return 'render_template(f"{error_code}.html"), error_code'

    for errcode in [401, 404, 500]:
        app.errorhandler(errcode)(render_error)
    return None


def register_shell_context(app: Flask):
    """Register shell context objects.
    注册shell上下文处理函数
    """

    def shell_context():
        """Shell context objects."""
        return {
            "db": db,
            "User": user.models.User,
            'Fund': fund.models.Fund,
            'FundMgr': fund.models.Mgr,
            'MidFundMgr': fund.models.FundMgr,
            'FundPortfolio': fund.models.FundPortfolio,
            'Account': account.models.Account,
        }

    # 当你使用flask shell命令启动Python Shell时，所有使用app.shell_context_processor装饰器注册的shell上下文处理函数
    # 都会被自动执行，这会将db和Note对象推送到Python Shell上下文里
    app.shell_context_processor(shell_context)


'''
TODO: 另一种写法
see also:https://github.com/miguelgrinberg/flasky/blob/29e3646db8185254f0c9f52522014f83ed095ece/flasky.py#L25
@app.shell_context_processor
def make_shell_context():
    return dict(db=db, User=User, Follow=Follow, Role=Role, Permission=Permission, Post=Post, Comment=Comment)
'''


def register_commands(app: Flask):
    """Register Click commands."""
    app.cli.add_command(commands.test)
    app.cli.add_command(commands.lint)
    # 添加指令
    app.cli.add_command(commands.init_db)
    app.cli.add_command(commands.update_db)


def configure_logger(app: Flask):
    """Configure loggers."""
    handler = logging.StreamHandler(sys.stdout)
    if not app.logger.handlers:
        app.logger.addHandler(handler)


def update_config(app: Flask):
    """除了setting中的配置，我们对一些根据不同环境（生产、测试、开发）的配置进行区分"""
    amend_conf = config.get(settings.ENV)
    logger.info(amend_conf)
    app.config.from_object(amend_conf)


#
# TODO:Optionally define and set unauthorized callbacks
# security.unauthz_handler(<your unauth handler>)

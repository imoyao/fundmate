# -*- coding: utf-8 -*-
"""The app module, containing the app factory function."""
import logging
import sys

from apiflask import APIFlask
from flask_praetorian import exceptions as praetorian_excepts

from backend.fundmate import account, commands, errors, fund, public, settings, user
from backend.fundmate.account import views as account_views
from backend.fundmate.config import config
from backend.fundmate.extensions import db, guard, loguru, mail, migrate
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund import views as fund_views
from backend.fundmate.public import views as public_views
from backend.fundmate.settings import env
from backend.fundmate.user import models as user_models
from backend.fundmate.user import views as user_views


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
    logger.info('Fund Mate has created!')
    '''
    RuntimeError: No application found. Either work inside a view function or push an application context. 
    See also: http://flask-sqlalchemy.pocoo.org/contexts/ .
    see also: https://blog.csdn.net/zhongqiushen/article/details/79162792
    '''
    app.app_context().push()
    return app


def register_extensions(app: APIFlask):
    """Register Flask extensions."""
    db.init_app(app)
    # **注意** 此处必须传入User 的定义 see also: https://github.com/dusktreader/flask-praetorian/issues/224
    guard.init_app(app, user_models.User)
    mail.init_app(app)
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


def register_blueprints(app: APIFlask):
    """Register Flask blueprints."""
    app.register_blueprint(public_views.bp)
    # 用户相关
    app.register_blueprint(user_views.bp)
    app.register_blueprint(fund_views.bp)
    # 账号相关
    app.register_blueprint(account_views.bp)
    return None


def register_error_handlers(app: APIFlask):
    """Register error handlers.
    https://github.com/frostming/flask-vue-todo/blob/e5330497bb0a5457778160aeff0082549214d06a/backend/__init__.py#L41
    https://thewebdev.info/2020/10/08/python-web-development-with-flask%E2%80%8A-%E2%80%8Aerror-handling/
    """

    @app.error_processor
    def render_error(error):
        """Render error template."""
        # If a HTTPException, pull the `code` attribute; default to 500
        error_code = getattr(error, "code", 500)
        detail = error.detail or error.message or None
        try:
            extra_data = error.extra_data
        except AttributeError:
            extra_data = {}
        body = {'message': detail, **extra_data}
        status_code = error.status_code or error_code
        headers = error.headers
        return body, status_code, headers

    @app.errorhandler(praetorian_excepts.PraetorianError)
    def handle_praetorian_error(e: praetorian_excepts.PraetorianError):
        """
        接管 PraetorianError，专门处理auth错误的处理器

        参阅：
        1. [Error Handling - APIFlask](
        https://apiflask.com/error-handling/#custom-error-classes)
        2. [Error Handling — flask-praetorian 1.3.0
        documentation](https://flask-praetorian.readthedocs.io/en/latest/notes.html#error-handling)

        :param e: PraetorianError 实例
        :return: 
        """
        cls_name = e.__class__.__name__
        msg = e.message or None
        status_code = getattr(e, 'status_code', 401)
        error_cls = getattr(praetorian_excepts, cls_name, praetorian_excepts.PraetorianError)
        extra_data = dict()
        if isinstance(e, error_cls):
            custom_error = getattr(errors, cls_name, errors.PraetorianError)
            custom_msg = custom_error.message
            extra_data = custom_error.extra_data
            extra_data['extra_msg'] = msg
        else:
            extra_data['error_cls'] = cls_name
            custom_msg = msg
            logger.error(f'Get {cls_name} with msg: {msg}')
        body = {'message': custom_msg, **extra_data}
        headers = e.headers
        return body, status_code, headers


def register_shell_context(app: APIFlask):
    """Register shell context objects.
    注册shell上下文处理函数
    """

    def shell_context():
        """Shell context objects."""
        return {
            "db": db,
            "User": user.models.User,
            "Role": user.models.Role,
            'Fund': fund.models.Fund,
            'FundMgr': fund.models.Mgr,
            'MidFundMgr': fund.models.FundMgr,
            'FeeRatio': fund.models.FeeRatio,
            'PurchaseRule': fund.models.PurchaseRule,
            'RedeemRule': fund.models.RedeemRule,
            'FundPortfolio': fund.models.FundPortfolio,
            'FundPortfolioMgr': fund.models.FundPortfolioMgr,
            'FundPortfolioAdjustHistory': fund.models.FundPortfolioAdjustHistory,
            'FundPortfolioHoldDetail': fund.models.FundPortfolioHoldDetail,
            'FundSaleOrg': fund.models.FundSaleOrg,
            'Account': account.models.Account,
        }

    # 当你使用flask shell命令启动Python Shell时，所有使用app.shell_context_processor装饰器注册的shell上下文处理函数
    # 都会被自动执行，这会将db和Note对象推送到Python Shell上下文里
    app.shell_context_processor(shell_context)


'''
另一种写法
see also:https://github.com/miguelgrinberg/flasky/blob/29e3646db8185254f0c9f52522014f83ed095ece/flasky.py#L25
@app.shell_context_processor
def make_shell_context():
    return dict(db=db, User=User, Follow=Follow, Role=Role, Permission=Permission, Post=Post, Comment=Comment)
'''


def register_commands(app: APIFlask):
    """Register Click commands."""
    app.cli.add_command(commands.test)
    app.cli.add_command(commands.lint)
    # 添加指令
    app.cli.add_command(commands.init_db)
    app.cli.add_command(commands.update_db)


def configure_logger(app: APIFlask):
    """Configure loggers."""
    handler = logging.StreamHandler(sys.stdout)
    if not app.logger.handlers:
        app.logger.addHandler(handler)


def update_config(app: APIFlask):
    """除了setting中的配置，我们对一些根据不同环境（生产、测试、开发）的配置进行区分"""
    amend_conf = config.get(settings.ENV)
    logger.info(amend_conf)
    app.config.from_object(amend_conf)

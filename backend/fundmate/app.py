# -*- coding: utf-8 -*-
"""The app module, containing the app factory function."""
import logging
import sys

from flask import Flask
from apiflask import APIFlask, Schema, input, output, abort

from backend.fundmate import account, commands, fund, public, settings, user
from backend.fundmate.config import config
from backend.fundmate.extensions import (bcrypt, cache, db,
                                         flask_static_digest, login_manager, loguru, migrate)

from .exts.flask_loguru import logger


def print_logo():
    logo_str = r'''
    
      ___           ___           ___                                  ___           ___                         ___     
     /\__\         /\  \         /\  \         _____                  /\  \         /\  \                       /\__\    
    /:/ _/_        \:\  \        \:\  \       /::\  \                |::\  \       /::\  \         ___         /:/ _/_   
   /:/ /\__\        \:\  \        \:\  \     /:/\:\  \               |:|:\  \     /:/\:\  \       /\__\       /:/ /\__\  
  /:/ /:/  /    ___  \:\  \   _____\:\  \   /:/  \:\__\            __|:|\:\  \   /:/ /::\  \     /:/  /      /:/ /:/ _/_ 
 /:/_/:/  /    /\  \  \:\__\ /::::::::\__\ /:/__/ \:|__|          /::::|_\:\__\ /:/_/:/\:\__\   /:/__/      /:/_/:/ /\__\
 \:\/:/  /     \:\  \ /:/  / \:\~~\~~\/__/ \:\  \ /:/  /          \:\~~\  \/__/ \:\/:/  \/__/  /::\  \      \:\/:/ /:/  /
  \::/__/       \:\  /:/  /   \:\  \        \:\  /:/  /            \:\  \        \::/__/      /:/\:\  \      \::/_/:/  / 
   \:\  \        \:\/:/  /     \:\  \        \:\/:/  /              \:\  \        \:\  \      \/__\:\  \      \:\/:/  /  
    \:\__\        \::/  /       \:\__\        \::/  /                \:\__\        \:\__\          \:\__\      \::/  /   
     \/__/         \/__/         \/__/         \/__/                  \/__/         \/__/           \/__/       \/__/    
                                                                            
    '''
    print(logo_str)


def create_app(config_object: str = "backend.fundmate.settings"):
    """Create application factory, as explained here: http://flask.pocoo.org/docs/patterns/appfactories/.

    :param config_object: The configuration object to use.
    """
    '''
    see also:[APIFlask](https://apiflask.com/#example)
    '''
    print_logo()
    app = APIFlask(__name__)
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
    RuntimeError: No application found. Either work inside a view function or push an application context. See http://flask-sqlalchemy.pocoo.org/contexts/.
    see also: https://blog.csdn.net/zhongqiushen/article/details/79162792
    '''
    app.app_context().push()
    return app


def register_extensions(app: Flask):
    """Register Flask extensions."""
    bcrypt.init_app(app)
    cache.init_app(app)
    db.init_app(app)
    # csrf_protect.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    flask_static_digest.init_app(app)
    loguru.init_app(app, {
        "LOG_PATH": "/home/work/www/log",
        "LOG_NAME": "run.log"
    })
    return None


def register_blueprints(app: Flask):
    """Register Flask blueprints."""
    app.register_blueprint(public.views.bp)
    app.register_blueprint(user.views.bp)
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
        return {"db": db, "User": user.models.User, 'Fund': fund.models.Fund, 'Account': account.models.Account}

    # 当你使用flask shell命令启动Python Shell时，所有使用app.shell_context_processor装饰器注册的shell上下文处理函数
    # 都会被自动执行，这会将db和Note对象推送到Python Shell上下文里
    app.shell_context_processor(shell_context)


def register_commands(app: Flask):
    """Register Click commands."""
    app.cli.add_command(commands.test)
    app.cli.add_command(commands.lint)
    # 添加指令
    app.cli.add_command(commands.init_db)
    app.cli.add_command(commands.create_db)


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

# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/7 21:19
# File : main.py
"""应用入口，使用工厂模式创建 APIFlask 实例."""

from dotenv import load_dotenv

load_dotenv()  # 必须在导入其他模块之前加载

import os  # noqa: E402
from pathlib import Path  # noqa: E402

import xalpha as xa  # noqa: E402
from apiflask import APIFlask  # noqa: E402
from flask import jsonify  # noqa: E402
from flask_cors import CORS  # noqa: E402

from app.core.database import init_db  # noqa: E402
from app.core.exceptions import ErrorCode, SBException  # noqa: E402
from app.domains.assets.views import bp as assets_bp  # noqa: E402
from app.domains.funds.views import bp as funds_bp  # noqa: E402
from app.domains.health import bp as health_bp  # noqa: E402
from app.domains.importers.views import importers_bp  # noqa: E402
from app.domains.ledgers.views import ledgers_bp  # noqa: E402
from app.domains.performance.views import bp as performance_bp  # noqa: E402
from app.domains.positions.views import bp as positions_bp  # noqa: E402
from app.domains.securities.views import bp as securities_bp  # noqa: E402
from app.domains.summary.views import bp as summary_bp  # noqa: E402
from app.domains.transactions.views import bp as transactions_bp  # noqa: E402
from app.domains.utils.views import utils_bp  # noqa: E402
from app.domains.watchlist.views import watchlist_bp as watchlist_bp  # noqa: E402


def create_app() -> APIFlask:
    """创建并配置 APIFlask 应用."""
    app = APIFlask(
        __name__,
        title='ShowBuy',
        version='0.1.0',
        docs_ui='swagger-ui',  # 启用 Swagger UI 文档
    )
    app.config['DEBUG'] = True
    app.config['PROPAGATE_EXCEPTIONS'] = True

    # ✅ 确保 xalpha 缓存目录存在
    cache_dir = Path('data/xalpha_cache')
    cache_dir.mkdir(parents=True, exist_ok=True)
    xa.set_backend(backend='csv', path=str(cache_dir))

    # ✅ 启用 CORS，允许前端跨域访问
    # 开发环境允许所有源，生产环境指定前端地址
    allowed_origins = os.getenv('CORS_ORIGINS', '*')
    if allowed_origins == '*':
        CORS(app, resources={r'/*': {'origins': '*'}})
    else:
        CORS(app, resources={r'/*': {'origins': allowed_origins.split(',')}})

    # 注册蓝图
    app.register_blueprint(health_bp)
    app.register_blueprint(positions_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(summary_bp)
    app.register_blueprint(securities_bp)
    app.register_blueprint(funds_bp)
    app.register_blueprint(watchlist_bp)
    app.register_blueprint(importers_bp)
    app.register_blueprint(ledgers_bp)
    app.register_blueprint(utils_bp)
    app.register_blueprint(performance_bp)

    # 初始化数据库
    with app.app_context():
        init_db()

    return app


def register_error_handlers(app: APIFlask):
    """注册全局异常处理器。"""

    @app.errorhandler(SBException)
    def handle_app_exception(e):
        """处理自定义业务异常。"""
        response = {
            'data': e.detail,
            'message': e.message,
            'error_code': e.code,
        }
        # 如果 detail 为空，不返回 data 字段或保持 data: null
        if not e.detail:
            response['data'] = None
        return jsonify(response), e.status_code

    @app.errorhandler(ValueError)
    def handle_value_error(e):
        """处理参数校验错误（如 Service 层抛出的 ValueError）。"""
        response = {
            'data': None,
            'message': str(e),
            'error_code': ErrorCode.INVALID_PARAMS.code,
        }
        return jsonify(response), 400

    @app.errorhandler(404)
    def handle_not_found(e):
        """处理 404 路由未找到。"""
        response = {
            'data': None,
            'message': '请求的资源不存在',
            'error_code': ErrorCode.RESOURCE_NOT_FOUND.code,
        }
        return jsonify(response), 404

    @app.errorhandler(500)
    def handle_internal_error(e):
        """处理未捕获的系统异常。"""
        # 记录完整堆栈（使用 loguru）
        from loguru import logger

        logger.opt(exception=True).error('未捕获的系统异常')
        response = {
            'data': None,
            'message': ErrorCode.INTERNAL_ERROR.msg,
            'error_code': ErrorCode.INTERNAL_ERROR.code,
        }
        return jsonify(response), 500


app = create_app()
register_error_handlers(app)

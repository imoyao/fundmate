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
from loguru import logger  # noqa: E402
from werkzeug.exceptions import HTTPException  # noqa: E402

from app.core.database import init_db  # noqa: E402
from app.core.exceptions import ErrorCode, SBException  # noqa: E402
from app.domains.assets.views import bp as assets_bp  # noqa: E402
from app.domains.funds.views import bp as funds_bp  # noqa: E402
from app.domains.health import bp as health_bp  # noqa: E402
from app.domains.importers.views import importers_bp  # noqa: E402
from app.domains.ledgers.views import ledgers_bp  # noqa: E402
from app.domains.performance.views import bp as performance_bp  # noqa: E402
from app.domains.portfolios.views import portfolios_bp  # noqa: E402
from app.domains.positions.views import bp as positions_bp  # noqa: E402
from app.domains.securities.views import bp as securities_bp  # noqa: E402
from app.domains.strategy.views import strategy_bp  # noqa: E402
from app.domains.summary.views import bp as summary_bp  # noqa: E402
from app.domains.temperature.views import thermometer_bp  # noqa: E402
from app.domains.transactions.views import bp as transactions_bp  # noqa: E402
from app.domains.utils.views import utils_bp  # noqa: E402
from app.domains.watchlist.views import watchlist_bp  # noqa: E402


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
    app.register_blueprint(portfolios_bp)
    app.register_blueprint(strategy_bp)
    app.register_blueprint(thermometer_bp)

    # 初始化数据库
    with app.app_context():
        init_db()

    # 注册全局异常处理器（统一 {data, message, error_code} 信封）。
    # 必须在 create_app() 内部注册，否则测试 fixture 直接调用 create_app()
    # 得到的 app 不会挂载处理器，导致错误契约在测试环境失效。
    register_error_handlers(app)

    return app


# HTTP 状态码 → 业务错误码 映射，用于把 abort() 抛出的 HTTPException
# 统一收敛到 SPEC 的 {data, message, error_code} 信封，避免框架默认响应绕过契约。
_HTTP_STATUS_TO_ERROR_CODE = {
    400: ErrorCode.INVALID_PARAMS,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.RESOURCE_NOT_FOUND,
    409: ErrorCode.DUPLICATE_ENTRY,
    422: ErrorCode.INVALID_PARAMS,
    500: ErrorCode.INTERNAL_ERROR,
    503: ErrorCode.DATA_SOURCE_ERROR,
    504: ErrorCode.DATA_SOURCE_TIMEOUT,
}


def register_error_handlers(app: APIFlask):
    """注册全局异常处理器。

    所有异常统一返回 {data, message, error_code} 信封，满足 SPEC 错误契约。
    abort() 抛出的 werkzeug HTTPException（400/404/409/500 等）也在此统一处理，
    不再依赖框架默认的 HTML 页面或裸 JSON 响应。
    APIFlask 的输入校验错误属于 HTTPError（非 HTTPException），由框架自带处理器
    返回 422 JSON（同样带 message 字段），此处不重复处理。
    """

    @app.errorhandler(SBException)
    def handle_app_exception(e: SBException):
        """处理自定义业务异常。"""
        response = {
            'data': e.detail if e.detail else None,
            'message': e.message,
            'error_code': e.code,
        }
        return jsonify(response), e.status_code

    @app.errorhandler(ValueError)
    def handle_value_error(e: ValueError):
        """处理参数校验错误（如 Service 层抛出的 ValueError）。"""
        response = {
            'data': None,
            'message': str(e),
            'error_code': ErrorCode.INVALID_PARAMS.code,
        }
        return jsonify(response), 400

    @app.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException):
        """统一处理 abort() 抛出的 HTTP 异常，返回信封。"""
        error_code = _HTTP_STATUS_TO_ERROR_CODE.get(e.code, ErrorCode.OPERATION_FAILED)
        message = e.description if e.description else error_code.msg
        response = {
            'data': None,
            'message': message,
            'error_code': error_code.code,
        }
        return jsonify(response), e.code

    @app.errorhandler(Exception)
    def handle_unexpected(e: Exception):
        """兜底：未预期的未知异常，避免泄露堆栈、统一 500 信封。"""
        logger.opt(exception=True).error('未捕获的系统异常')
        response = {
            'data': None,
            'message': ErrorCode.INTERNAL_ERROR.msg,
            'error_code': ErrorCode.INTERNAL_ERROR.code,
        }
        return jsonify(response), 500


app = create_app()

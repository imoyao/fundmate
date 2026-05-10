# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/7 21:19
# File : main.py
"""应用入口，使用工厂模式创建 APIFlask 实例."""

from apiflask import APIFlask
from flask_cors import CORS

from app.core.database import init_db
from app.domains.health import bp as health_bp
from app.domains.positions.summary import bp as summary_bp
from app.domains.positions.views import bp as positions_bp
from app.domains.transactions.views import bp as transactions_bp


def create_app() -> APIFlask:
    """创建并配置 APIFlask 应用."""
    app = APIFlask(
        __name__,
        title='ShowBuy',
        version='0.1.0',
        docs_ui='swagger-ui',  # 启用 Swagger UI 文档
    )

    # ✅ 启用 CORS，允许前端跨域访问
    CORS(app, resources={r'/*': {'origins': '*'}})

    # 注册蓝图
    app.register_blueprint(health_bp)
    app.register_blueprint(positions_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(summary_bp)

    # 初始化数据库
    with app.app_context():
        init_db()

    return app


app = create_app()

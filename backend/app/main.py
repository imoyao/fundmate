# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/7 21:19
# File : main.py
"""应用入口，使用工厂模式创建 APIFlask 实例."""

from apiflask import APIFlask

from app.database import init_db


def create_app() -> APIFlask:
    """创建并配置 APIFlask 应用."""
    app = APIFlask(
        __name__,
        title='ShowBuy',
        version='0.1.0',
        docs_ui='swagger-ui',  # 启用 Swagger UI 文档
    )

    # 注册蓝图
    from app.api.health import bp as health_bp

    app.register_blueprint(health_bp)

    from app.api.positions import bp as positions_bp

    app.register_blueprint(positions_bp)

    from app.api.summary import bp as summary_bp

    app.register_blueprint(summary_bp)

    # 初始化数据库
    with app.app_context():
        init_db()

    return app


app = create_app()

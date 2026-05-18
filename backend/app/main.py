# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/7 21:19
# File : main.py
"""应用入口，使用工厂模式创建 APIFlask 实例."""

from pathlib import Path

import xalpha as xa
from apiflask import APIFlask
from flask_cors import CORS

from app.core.database import init_db
from app.domains.assets.views import bp as assets_bp
from app.domains.funds.views import bp as funds_bp
from app.domains.health import bp as health_bp
from app.domains.importers.views import importers_bp
from app.domains.ledgers.views import ledgers_bp
from app.domains.positions.views import bp as positions_bp
from app.domains.securities.views import bp as securities_bp
from app.domains.summary.views import bp as summary_bp
from app.domains.transactions.views import bp as transactions_bp
from app.domains.watchlist.views import watchlist_bp as watchlist_bp


def create_app() -> APIFlask:
    """创建并配置 APIFlask 应用."""
    app = APIFlask(
        __name__,
        title='ShowBuy',
        version='0.1.0',
        docs_ui='swagger-ui',  # 启用 Swagger UI 文档
    )

    # ✅ 确保 xalpha 缓存目录存在
    cache_dir = Path('data/xalpha_cache')
    cache_dir.mkdir(parents=True, exist_ok=True)
    xa.set_backend(backend='csv', path=str(cache_dir))

    # ✅ 启用 CORS，允许前端跨域访问
    CORS(app, resources={r'/*': {'origins': '*'}})

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
    # 初始化数据库
    with app.app_context():
        init_db()

    return app


app = create_app()

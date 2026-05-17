# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 23:00
# File : conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.domains.assets.models
import app.domains.funds.models

# 强制导入所有模型，确保它们注册到 Base
import app.domains.positions.models
import app.domains.securities.models
import app.domains.transactions.models
import app.domains.watchlist.models
from app.core.database import Base
from app.main import create_app


@pytest.fixture
def app(monkeypatch):
    """创建使用完全隔离内存数据库的测试应用"""
    # 关键：使用 StaticPool 确保所有连接指向同一个内存数据库
    test_engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # 替换全局 engine 和 SessionLocal
    monkeypatch.setattr('app.core.database.engine', test_engine)
    monkeypatch.setattr('app.core.database.SessionLocal', TestSessionLocal)

    # 在应用启动前创建所有表
    Base.metadata.create_all(bind=test_engine)

    # 创建应用（内部 init_db 会再次 create_all，安全无影响）
    app = create_app()
    app.config['TESTING'] = True
    yield app


@pytest.fixture
def client(app):
    """提供测试客户端"""
    with app.test_client() as client:
        yield client


@pytest.fixture
def db(app):
    """提供测试专用数据库会话（已绑定内存引擎）"""
    from app.core.database import SessionLocal  # 延迟导入，确保使用 patched 版本

    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def clean_db(app):
    """每个测试结束后自动清空所有表，保证隔离"""
    yield
    from app.core.database import SessionLocal  # 延迟导入

    session = SessionLocal()
    # 按依赖逆序删除，避免外键错误
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()

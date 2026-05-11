# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/10 23:00
# File : conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.domains.assets.models
import app.domains.funds.models

# 确保所有模型已导入
import app.domains.positions.models
import app.domains.securities.models
import app.domains.transactions.models
from app.core.database import Base
from app.main import create_app


@pytest.fixture
def app(monkeypatch):
    """创建使用完全隔离内存数据库的测试应用"""
    # 1. 建立内存引擎并替换模块级变量
    test_engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False})
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr('app.core.database.engine', test_engine)
    monkeypatch.setattr('app.core.database.SessionLocal', test_session_local)

    # 2. 建表（此时 engine 已为内存引擎）
    Base.metadata.create_all(bind=test_engine)

    # 3. 创建应用（内部的 init_db 会再次 create_all，无副作用）
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

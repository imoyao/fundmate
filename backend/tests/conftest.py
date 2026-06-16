# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 23:00
# File : conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.domains.assets.models  # noqa: F401
import app.domains.funds.models  # noqa: F401

# 强制导入所有模型，确保它们注册到 Base
import app.domains.positions.models  # noqa: F401
import app.domains.price_history.models  # noqa: F401
import app.domains.securities.models  # noqa: F401
import app.domains.transactions.models  # noqa: F401
import app.domains.watchlist.models  # noqa: F401
from app.core.database import Base
from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.positions.models import Position
from app.main import create_app


@pytest.fixture
def app(monkeypatch):
    test_engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    monkeypatch.setattr('app.core.database.engine', test_engine)
    monkeypatch.setattr('app.core.database.SessionLocal', TestSessionLocal)

    # 彻底禁用异步回填线程（直接替换已导入的引用）
    import app.services.importer.orchestrator
    import app.services.position_service

    monkeypatch.setattr(app.services.position_service, 'trigger_backfill', lambda *a, **kw: None)
    monkeypatch.setattr(app.services.importer.orchestrator, 'trigger_backfill', lambda *a, **kw: None)

    Base.metadata.create_all(bind=test_engine)

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


def make_position(db, **kwargs):
    """构造 Position 时自动转换金额/份额到内部单位"""
    if 'quantity' in kwargs:
        kwargs['quantity'] = Money.shares_to_min_unit(kwargs['quantity'])
    if 'avg_price' in kwargs:
        kwargs['avg_price'] = Money.yuan_to_cents(kwargs['avg_price'])
    if 'current_price' in kwargs:
        kwargs['current_price'] = Money.yuan_to_cents(kwargs['current_price'])
    pos = Position(**kwargs)
    db.add(pos)
    db.commit()
    return pos


def make_asset(db, **kwargs):
    """构造 Asset 时自动转换 amount 到分"""
    if 'amount' in kwargs:
        kwargs['amount'] = Money.yuan_to_cents(kwargs['amount'])
    asset = Asset(**kwargs)
    db.add(asset)
    db.commit()
    return asset

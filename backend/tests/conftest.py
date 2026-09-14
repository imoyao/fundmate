# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 23:00
# File : conftest.py
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.domains.assets.models  # noqa: F401
import app.domains.families.models  # noqa: F401
import app.domains.funds.models  # noqa: F401
import app.domains.indices.models  # noqa: F401
import app.domains.positions.models  # noqa: F401
import app.domains.price_history.models  # noqa: F401
import app.domains.securities.models  # noqa: F401
import app.domains.summary.models  # noqa: F401
import app.domains.transactions.models  # noqa: F401
import app.domains.users.models  # noqa: F401
import app.domains.watchlist.models  # noqa: F401
from app.core.database import Base
from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.main import create_app


@pytest.fixture
def app(monkeypatch):
    test_engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    monkeypatch.setattr('app.core.database.engine', test_engine)
    monkeypatch.setattr('app.core.database.user_engine', test_engine)
    monkeypatch.setattr('app.core.database.SessionLocal', TestSessionLocal)

    # 双库架构支持：reconciliation 等 user 域表经 user_session 访问。
    # 测试需把 user_session 与 get_db(SessionLocal) 指向同一内存库，保证测试数据可见；
    # market 域会话保持独立内存库，满足「user/market 分库」断言（test_db_data_domain）。
    market_engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestMarketSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=market_engine)
    import app.core.db_factory as _db_factory

    monkeypatch.setattr(_db_factory, 'user_session_factory', lambda: TestSessionLocal)
    monkeypatch.setattr(_db_factory, 'market_session_factory', lambda: TestMarketSessionLocal)

    # 彻底禁用异步回填线程（直接替换已导入的引用）
    # #1370：orchestrator 拆分后 trigger_backfill 的调用点在 orchestrator_commit
    import app.services.importer.orchestrator_commit
    import app.services.position_service

    monkeypatch.setattr(app.services.position_service, 'trigger_backfill', lambda *a, **kw: None)
    monkeypatch.setattr(app.services.importer.orchestrator_commit, 'trigger_backfill', lambda *a, **kw: None)

    Base.metadata.create_all(bind=test_engine)
    Base.metadata.create_all(bind=market_engine)

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
def _patch_thermo_session(app, monkeypatch):
    # service 模块在 import 时早绑定了 app.core.database.SessionLocal，
    # 而 app fixture 把 app.core.database.SessionLocal 重定向到内存引擎，
    # monkeypatch 改模块属性只对 app.core.database 生效，对 service 模块的早绑定无效，
    # 会导致 TemperatureService 连到真实库。此处把 service.SessionLocal 对齐到内存引擎，
    # 修复测试隔离隐患（原本只有 test_thermometer_overview.py 局部处理）。
    import app.services.thermometer.service as thermo_service
    from app.core.database import SessionLocal as PatchedSessionLocal

    monkeypatch.setattr(thermo_service, 'SessionLocal', PatchedSessionLocal)

    # ocr_service 重构后（P1，ai_recognizer 分层）业务逻辑迁往 ai_recognizer.guards；
    # guards 同样早绑定了 SessionLocal，对齐到内存引擎，避免连真实库
    import app.services.ai_recognizer.guards as ai_guards

    monkeypatch.setattr(ai_guards, 'SessionLocal', PatchedSessionLocal)


@pytest.fixture(autouse=True)
def _disable_async_backfill(monkeypatch):
    """禁用创建自选/持仓时触发的异步回填后台线程（2026-09-09）。

    trigger_backfill 起 daemon 线程跑 akshare/xalpha 适配器：既在测试里发真实
    网络请求（偶发超时/flaky），又因 async_backfill 顶层 from-import 早绑定了
    真实 SessionLocal 而绕过内存库、直接写开发库。与 _patch_thermo_session
    同类的早绑定隐患，但正确做法不是对齐会话（不该跑），而是整体禁用。
    注意消费方均为 from-import 绑定，须逐个 patch 其模块属性。"""
    _noop = lambda *a, **k: None  # noqa: E731

    import importlib

    monkeypatch.setattr('app.services.async_backfill.trigger_backfill', _noop)
    for mod_name in (
        'app.services.watchlist_service',
        'app.services.position_service',
        'app.services.importer.orchestrator',
    ):
        monkeypatch.setattr(importlib.import_module(mod_name), 'trigger_backfill', _noop, raising=False)


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


# -------------------- 测试辅助 fixtures --------------------
def _ensure_ledger(db, name, ledger_type='bank', family_id=1):
    ledger = db.query(Ledger).filter_by(name=name, family_id=family_id).first()
    if not ledger:
        ledger = Ledger(name=name, ledger_type=ledger_type, family_id=family_id)
        db.add(ledger)
        db.flush()
    return ledger.id


@pytest.fixture
def make_position(db):
    def _make(**kwargs):
        if 'family_id' not in kwargs:
            kwargs['family_id'] = 1
        if 'ledger_id' not in kwargs and 'account_name' in kwargs:
            kwargs['ledger_id'] = _ensure_ledger(db, kwargs['account_name'], family_id=kwargs['family_id'])
        if 'quantity' in kwargs:
            kwargs['quantity'] = Money.shares_to_min_unit(kwargs['quantity'])
        if 'avg_price' in kwargs:
            kwargs['avg_price'] = Money.yuan_to_price_units(kwargs['avg_price'])
        if 'current_price' in kwargs:
            kwargs['current_price'] = Money.yuan_to_price_units(kwargs['current_price'])
        pos = Position(**kwargs)
        db.add(pos)
        db.commit()
        return pos

    return _make


@pytest.fixture
def make_asset(db):
    def _make(**kwargs):
        if 'family_id' not in kwargs:
            kwargs['family_id'] = 1
        if 'ledger_id' not in kwargs and 'account_name' in kwargs:
            kwargs['ledger_id'] = _ensure_ledger(db, kwargs['account_name'], family_id=kwargs['family_id'])
        if 'amount' in kwargs:
            kwargs['amount'] = Money.yuan_to_cents(kwargs['amount'])
        asset = Asset(**kwargs)
        db.add(asset)
        db.commit()
        return asset

    return _make


@pytest.fixture
def make_transaction(db):
    """
    生成一条交易记录 (Transaction) 的 Fixture。
    自动处理金额、价格、数量的分/最小单位转换。
    """

    def _make_transaction(
        position_id: int,
        ledger_id: int,
        txn_type: str = 'buy',
        quantity: float = 100.0,
        price: float = 1.0,
        amount: float = None,
        confirm_date: date = None,  # 确认日，用 date 类型
        trade_date: datetime = None,  # 🔥 交易日期，统一改成 datetime 类型
        account_name: str = None,
        position_name: str = '测试持仓',
        symbol: str = '000001',
        allow_null_trade_date: bool = False,  # 允许 trade_date 存 NULL（契约测试：缺失回退 confirm_date）
        **kwargs,
    ):
        # 兜底日期
        from datetime import datetime

        if trade_date is None and not allow_null_trade_date:
            # ✅ 保证存入数据库的是带时间的 datetime 对象
            trade_date = datetime.now()
        if confirm_date is None:
            confirm_date = (trade_date or datetime.now()).date()  # 从 datetime 中提取 date

        if amount is None:
            amount = quantity * price

        txn = Transaction(
            position_id=position_id,
            ledger_id=ledger_id,
            family_id=1,
            txn_type=txn_type,
            symbol=symbol,
            position_name=position_name,
            account_name=account_name or '测试账户',
            quantity=Money.shares_to_min_unit(quantity),
            price=Money.yuan_to_price_units(price),
            amount=Money.yuan_to_cents(amount),
            confirm_date=confirm_date,
            trade_date=trade_date,
            status='success',
            **kwargs,
        )
        db.add(txn)
        db.flush()
        return txn

    return _make_transaction

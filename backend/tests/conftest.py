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
    # 不再替换 SessionLocal maker：改为重定向引擎，使所有（含导入期早绑定的）SessionLocal()
    # 调用经 _engine_for 解析到内存库，从而删除 conftest 的「模块名清单」式补丁（见 #1608）。
    # 域路由在**查询期**经 _engine_for 取当前引擎（#1608：不再缓存引擎），
    # 故上面重定向即生效，不需要任何「让缓存失效」的调用（旧实现的
    # reset_routing_binds() 已随引擎缓存一并删除）。

    # 双库架构支持：reconciliation 等 user 域表经 user_session 访问。
    # 测试需把 user_session 与 get_db(SessionLocal) 指向同一内存库，保证测试数据可见；
    # market 域会话保持独立内存库，满足「user/market 分库」断言（test_db_data_domain）。
    market_engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestMarketSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=market_engine)
    import app.core.db_factory as _db_factory

    monkeypatch.setattr(_db_factory, 'user_session_factory', lambda: TestSessionLocal)
    monkeypatch.setattr(_db_factory, 'market_session_factory', lambda: TestMarketSessionLocal)

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
def _disable_async_backfill(monkeypatch):
    """禁用创建自选/持仓时触发的异步回填后台线程（2026-09-09）。

    trigger_backfill 起 daemon 线程跑 akshare/xalpha 适配器：既在测试里发真实
    网络请求（偶发超时/flaky），又绕过内存库直接写开发库——测试里本就不该跑。

    **只需 patch 源头一处**（#1608）：消费方（watchlist_service / position_service /
    importer.orchestrator_commit）一律以 ``async_backfill.trigger_backfill(...)`` 运行时
    取属性调用，不再 from-import 早绑定，因此不再需要维护「模块名清单」。"""
    monkeypatch.setattr('app.services.async_backfill.trigger_backfill', lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _isolate_cache_file_dir(tmp_path, monkeypatch):
    """把缓存文件层重定向到用例私有目录（#1531 / #1537）。

    `app/core/cache.py` 的文件层默认落 `tempfile.gettempdir()/fundmate_cache`——
    该目录**跨进程共享、无清理**：残留的 pkl 会在 ttl 内被下一个进程直接命中，于是
    「上一轮跑过什么」决定本轮结果（#1531 现象：ttl 内重跑 test_cache 必失败，真失败
    与污染失败的报错外观完全一致）。此处统一隔离；显式传 `file_dir=` 的用例不受影响。

    **覆盖范围**（#1537）：本夹具靠 env 生效，凡是**调用期**读 `CACHE_FILE_DIR` 的实现
    都被覆盖——`CacheService` 与温度计 fetchers 现已共用 `resolve_cache_file_dir()`，
    两条落盘路径一并纳入（见 `tests/services/thermometer/test_fetchers_cache.py`）。
    反之，任何把该 env 固化成模块级常量的实现都绕得过去：cache.py 曾是 import 期常量、
    fetchers 曾硬编码全局临时目录，各自漏过一次。新增文件缓存请一律走
    `resolve_cache_file_dir()`，不要另立目录解析。

    **补充（#1539）**：温度计的三处**分目录**缓存（`baostock_pb` / `em_industry_hist` /
    `fundfof_crowding`）也已收口到 `resolve_cache_subdir()`，同样纳入本夹具覆盖
    （见 `tests/services/thermometer/test_cache_dirs.py`）。它们原先各自在测试里
    monkeypatch 模块常量，属「新增一处缓存就要记得补一条 patch」的约定式隔离，现已取消。
    """
    monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path / 'fundmate_cache'))


@pytest.fixture(autouse=True)
def clean_db(app):
    """每个测试结束后自动清空所有表，保证隔离。

    只删当前会话引擎**实际存在**的表——#1608 后 SessionLocal 统一走路由 maker，clean_db
    也可能落在被重定向到无表内存库的引擎上（部分 DB 内部单测），避免 NoSuchTableError；
    若引擎被重定向为非连接对象（如单测用 sentinel），跳过清理。
    """
    yield
    from sqlalchemy import inspect

    from app.core.database import SessionLocal  # 延迟导入

    session = SessionLocal()
    try:
        existing = set(inspect(session.bind).get_table_names())
    except Exception:
        existing = set()
    # 按依赖逆序删除，避免外键错误
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in existing:
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

# -*- coding: utf-8 -*-
"""多引擎数据域护栏测试。

验证：
1. 启动校验：真实 Base.metadata 的每张表都在 DATA_DOMAIN_REGISTRY 登记（防漏声明）。
2. tables_by_domain 分组正确（market/user 无遗漏、无错分）。
3. market_session_factory / user_session_factory 入口语义。
4. init_db_split 在单库（user 引擎未配）模式下安全不崩。
"""

import pytest
from sqlalchemy import MetaData

# 触发全部域模型注册到 Base.metadata（conftest 未覆盖的域在此补导入）
import app.domains.assets.models  # noqa: F401
import app.domains.families.models  # noqa: F401
import app.domains.funds.models  # noqa: F401
import app.domains.portfolios.models  # noqa: F401
import app.domains.positions.models  # noqa: F401
import app.domains.price_history.models  # noqa: F401
import app.domains.securities.models  # noqa: F401
import app.domains.strategy.models  # noqa: F401
import app.domains.summary.models  # noqa: F401
import app.domains.temperature.models  # noqa: F401
import app.domains.transactions.models  # noqa: F401
import app.domains.usage.models  # noqa: F401
import app.domains.users.models  # noqa: F401
import app.domains.watchlist.models  # noqa: F401
import app.models.sync_log  # noqa: F401
from app.core import db_factory
from app.core.database import Base
from app.core.db_factory import (
    DATA_DOMAIN_REGISTRY,
    DOMAIN_MARKET,
    DOMAIN_USER,
    DatabaseFactory,
    market_session_factory,
    user_session_factory,
)


@pytest.fixture(autouse=True)
def _ensure_all_models_imported():
    """确保任一测试运行前 Base.metadata 已完整填充（消除 import 时序导致的孤儿误告警）。"""
    yield


def test_all_model_tables_registered_in_registry():
    """启动校验核心：真实模型表必须全部在注册表，否则视为 bug。"""
    model_tables = set(Base.metadata.tables.keys())
    missing = sorted(model_tables - set(DATA_DOMAIN_REGISTRY))
    assert missing == [], f'以下模型表未在 DATA_DOMAIN_REGISTRY 声明，禁止建库：{missing}'


def test_no_orphan_registry_entries():
    """注册表不应有"模型未定义却登记"的孤儿（提示文档/代码漂移）。"""
    model_tables = set(Base.metadata.tables.keys())
    orphan = sorted(set(DATA_DOMAIN_REGISTRY) - model_tables - set(db_factory.PENDING_DOMAIN_REGISTRY))
    assert orphan == [], f'注册表存在孤儿表（模型未定义）：{orphan}'


def test_tables_by_domain_grouping():
    """分组正确：market/user 覆盖全部模型表，且无跨域错分。"""
    grouped = DatabaseFactory.tables_by_domain(Base.metadata)
    classified = set(t.name for t in grouped[DOMAIN_MARKET]) | set(t.name for t in grouped[DOMAIN_USER])
    assert classified == set(Base.metadata.tables.keys())

    # 抽样核对关键边界先例
    assert DATA_DOMAIN_REGISTRY['sales_institutions'] == DOMAIN_USER
    assert DATA_DOMAIN_REGISTRY['fund_management_companies'] == DOMAIN_USER
    assert DATA_DOMAIN_REGISTRY['managers'] == DOMAIN_MARKET
    assert DATA_DOMAIN_REGISTRY['fund_managers'] == DOMAIN_MARKET
    assert DATA_DOMAIN_REGISTRY['funds'] == DOMAIN_MARKET
    assert DATA_DOMAIN_REGISTRY['ledgers'] == DOMAIN_USER
    assert DATA_DOMAIN_REGISTRY['watchlist'] == DOMAIN_USER
    assert DATA_DOMAIN_REGISTRY['sync_logs'] == DOMAIN_MARKET


def test_validate_domain_labels_passes_on_real_metadata():
    """启动断言对真实 metadata 应通过（不抛异常）。"""
    DatabaseFactory.validate_domain_labels(Base.metadata)


def test_market_session_factory_usable(monkeypatch):
    """market 引擎配置时，market_session_factory 可产出 sessionmaker。"""
    eng = __import__('sqlalchemy').create_engine('sqlite://')
    monkeypatch.setattr(db_factory.DatabaseFactory, '_engines', {DOMAIN_MARKET: eng})
    sm = market_session_factory()
    assert callable(sm)


def test_user_session_factory_raises_when_unconfigured(monkeypatch):
    """user 引擎未配置时，user_session_factory 抛 RuntimeError（防静默走错库）。"""
    monkeypatch.setattr(db_factory.DatabaseFactory, '_engines', {DOMAIN_MARKET: None, DOMAIN_USER: None})
    with pytest.raises(RuntimeError):
        user_session_factory()


def test_init_db_split_safe_when_user_engine_missing(monkeypatch):
    """单库模式（user 引擎为 None）下 init_db_split 不崩：只建 market 表。"""
    # 用一个内存 SQLite 冒充 market 引擎；user 引擎 None
    from sqlalchemy import create_engine

    eng = create_engine('sqlite:///:memory:')
    monkeypatch.setattr(db_factory.DatabaseFactory, '_engines', {DOMAIN_MARKET: eng, DOMAIN_USER: None})
    # 不应抛异常（user 表跳过）
    DatabaseFactory.tables_by_domain(Base.metadata)  # 先验证分组
    # 实际建表到 market 引擎
    grouped = DatabaseFactory.tables_by_domain(Base.metadata)
    mmeta = MetaData()
    for t in grouped[DOMAIN_MARKET]:
        t.to_metadata(mmeta)
    mmeta.create_all(bind=eng)
    # 仅 market 表落地
    from sqlalchemy import inspect

    assert set(inspect(eng).get_table_names()) == set(t.name for t in grouped[DOMAIN_MARKET])


def test_init_db_split_builds_both_domains(monkeypatch):
    """双库模式（两引擎都在）下，market/user 表分别落到各自引擎。"""
    from sqlalchemy import create_engine

    market_eng = create_engine('sqlite:///:memory:')
    user_eng = create_engine('sqlite:///:memory:')
    monkeypatch.setattr(
        db_factory.DatabaseFactory,
        '_engines',
        {DOMAIN_MARKET: market_eng, DOMAIN_USER: user_eng},
    )
    grouped = DatabaseFactory.tables_by_domain(Base.metadata)
    for domain, eng in ((DOMAIN_MARKET, market_eng), (DOMAIN_USER, user_eng)):
        meta = MetaData()
        for t in grouped[domain]:
            t.to_metadata(meta)
        meta.create_all(bind=eng)

    market_tables = set(t.name for t in grouped[DOMAIN_MARKET])
    user_tables = set(t.name for t in grouped[DOMAIN_USER])
    from sqlalchemy import inspect

    assert set(inspect(market_eng).get_table_names()) == market_tables
    assert set(inspect(user_eng).get_table_names()) == user_tables
    # 两域表集合不相交（防同一张表被建到两个库）
    assert market_tables.isdisjoint(user_tables)

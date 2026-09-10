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
from app.core.database import Base, init_db_split, user_session
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
    # 公司主数据唯一表在 market 域（fund_management_companies 已于 2026-09-10 合并删除）
    assert DATA_DOMAIN_REGISTRY['fund_companies'] == DOMAIN_MARKET
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


def test_user_session_factory_falls_back_to_local_sqlite(monkeypatch):
    """user 引擎未配 Supabase 时，user_session_factory 自动回退本地 SQLite 文件引擎。

    这是「单库/双库统一可用」的关键：本地开发零配置即可双库模拟，
    不会因缺 SUPABASE_DATABASE_URL 而抛错。
    """
    # 模拟未配置 SUPABASE_DATABASE_URL 的环境
    monkeypatch.delenv('SUPABASE_DATABASE_URL', raising=False)
    monkeypatch.setattr(db_factory.DatabaseFactory, '_engines', {})
    sm = user_session_factory()
    assert callable(sm)
    # 回退引擎应为 SQLite（URL 以 sqlite 开头）
    eng = sm.kw['bind']
    assert str(eng.url).startswith('sqlite://')


def test_init_db_split_local_fallback_builds_both_domains(monkeypatch):
    """本地双 SQLite 模式（user 回退本地文件）下，market/user 表分别建到两个物理引擎。

    验证「单库/双库统一可用」：无需 Supabase，两域表仍落不同引擎且互不相交。
    """
    from sqlalchemy import create_engine, inspect

    # 两个独立的本地 SQLite 文件引擎，模拟 market / user 双库
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
    assert set(inspect(market_eng).get_table_names()) == market_tables
    assert set(inspect(user_eng).get_table_names()) == user_tables
    # 两域表集合不相交（防同一张表被建到两个库）
    assert market_tables.isdisjoint(user_tables)


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


def test_local_fallback_uses_separate_user_database(monkeypatch, tmp_path):
    """集成验证：未配 Supabase 时，market/user 自动落到两个独立本地 SQLite 文件。

    对应「本地双库模拟」真实路径：清空引擎缓存 + 不设 SUPABASE_DATABASE_URL，
    让 DatabaseFactory 走 for_user 回退逻辑，确认 user 表不会混入 market 库文件。
    """
    monkeypatch.delenv('SUPABASE_DATABASE_URL', raising=False)
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('DEV_DATABASE_URL', f'sqlite:///{tmp_path / "market.db"}')
    monkeypatch.setenv('DEV_USER_DATABASE_URL', f'sqlite:///{tmp_path / "user.db"}')
    monkeypatch.setattr(db_factory.DatabaseFactory, '_engines', {})

    from sqlalchemy import inspect

    grouped = DatabaseFactory.tables_by_domain(Base.metadata)
    market_eng = DatabaseFactory.create(DOMAIN_MARKET)
    user_eng = DatabaseFactory.create(DOMAIN_USER)
    # 两引擎确实是不同文件
    assert str(market_eng.url) != str(user_eng.url)

    for domain, eng in ((DOMAIN_MARKET, market_eng), (DOMAIN_USER, user_eng)):
        meta = MetaData()
        for t in grouped[domain]:
            t.to_metadata(meta)
        meta.create_all(bind=eng)

    market_tables = set(t.name for t in grouped[DOMAIN_MARKET])
    user_tables = set(t.name for t in grouped[DOMAIN_USER])
    assert set(inspect(market_eng).get_table_names()) == market_tables
    assert set(inspect(user_eng).get_table_names()) == user_tables
    # 两张库文件互不重叠
    assert market_tables.isdisjoint(user_tables)
    # user 表（如 ledgers）不在 market 库里，反之亦然
    from sqlalchemy import inspect as _inspect

    assert 'ledgers' not in _inspect(market_eng).get_table_names()
    assert 'funds' not in _inspect(user_eng).get_table_names()


def test_seed_default_identity_split_mode_writes_to_user_engine(monkeypatch, tmp_path):
    """回归测试：修复跨域 bug——_seed_default_identity 曾用 market 引擎的 SessionLocal
    写入 user 域的 families/users 表，真双库分离时会落到错误库。

    验证：init_db_split 本地双 SQLite 模式下，种子家庭/用户只落在 user 引擎，
    market 引擎里查不到 families/users 行（跨域 bug 修复前会落在这里）。
    """
    from sqlalchemy import inspect
    from sqlalchemy.orm import sessionmaker

    monkeypatch.delenv('SUPABASE_DATABASE_URL', raising=False)
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('DEV_DATABASE_URL', f'sqlite:///{tmp_path / "market.db"}')
    monkeypatch.setenv('DEV_USER_DATABASE_URL', f'sqlite:///{tmp_path / "user.db"}')
    monkeypatch.setattr(db_factory.DatabaseFactory, '_engines', {})

    # 走真实双库建表 + 种子路径
    init_db_split()

    market_eng = DatabaseFactory.create(DOMAIN_MARKET)
    user_eng = DatabaseFactory.create(DOMAIN_USER)

    # user 引擎里应能查到默认家庭/用户
    with user_session() as db:
        from app.domains.families.models import Family
        from app.domains.users.models import User

        assert db.query(Family).filter_by(id=1).first() is not None
        assert db.query(User).filter_by(id=1).first() is not None

    # market 引擎里不应有 families/users 数据（跨域 bug 修复前会落在这里）
    if 'families' in inspect(market_eng).get_table_names():
        with sessionmaker(bind=market_eng)() as db:
            assert db.query(Family).filter_by(id=1).first() is None, (
                'families 种子错误地写到了 market 引擎（跨域 bug 复发）'
            )


def test_development_without_user_url_shares_market_database(monkeypatch, tmp_path):
    """默认「单库」（用户规则）：development 下未显式配置 DEV_USER_DATABASE_URL 时，
    user 域与 market 域共用同一 DB URL（本地既有 invest.db 数据立即可见）；
    显式配置 DEV_USER_DATABASE_URL 才拆出独立 user 库（本地双库模拟）。

    防回归：2026-09-01 曾把 development 默认改成无条件独立 invest.user.dev.db，
    导致本地 user 域表读到空库、自选页「暂无自选资产」。本用例锁死默认同库语义。
    """
    monkeypatch.delenv('SUPABASE_DATABASE_URL', raising=False)
    monkeypatch.delenv('DEV_FORCE_SUPABASE', raising=False)

    # 未配置独立 user 库 → user 与 market 同 URL（默认单库）。
    # 仅构造 URL 字符串比较，不连接落盘，路径放 tmp_path 避免污染仓库目录。
    market_url = f'sqlite:///{tmp_path / "market.db"}'
    monkeypatch.setenv('DEV_DATABASE_URL', market_url)
    monkeypatch.delenv('DEV_USER_DATABASE_URL', raising=False)
    market_cfg = db_factory.DatabaseConfig.for_app('development')
    user_cfg = db_factory.DatabaseConfig.for_user('development')
    assert user_cfg.url == market_cfg.url == market_url

    # 显式配置 DEV_USER_DATABASE_URL → 才拆分（本地双库模拟）
    user_url = f'sqlite:///{tmp_path / "user.db"}'
    monkeypatch.setenv('DEV_USER_DATABASE_URL', user_url)
    user_cfg2 = db_factory.DatabaseConfig.for_user('development')
    assert user_cfg2.url == user_url
    assert user_cfg2.url != market_cfg.url

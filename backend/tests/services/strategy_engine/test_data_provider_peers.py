# -*- coding: utf-8 -*-
"""行为画像取数层测试（#2382）——fund_type_id_of / peer_year_returns。

用 conftest 的内存双库（user/market 分离），只写 market 域数据。
"""

from datetime import date, timedelta

import pytest

D0 = date(2025, 1, 1)


@pytest.fixture
def market_db(app):
    """market 域内存会话（与 app fixture 同一引擎）。"""
    from app.core import db_factory

    session = db_factory.market_session_factory()()
    yield session
    session.close()


@pytest.fixture
def provider(app, market_db):
    from app.services.strategy_engine.data_provider import DataProvider

    return DataProvider(db=market_db, market_db=market_db)


def _mk_fund_type(session, name: str) -> int:
    from app.domains.funds.models import FundType

    ft = FundType(name=name)
    session.add(ft)
    session.flush()
    return ft.id


def _mk_fund(session, code: str, type_id: int) -> None:
    from app.domains.funds.models import Fund

    session.add(Fund(fund_code=code, name=f'基金{code}', fund_type_id=type_id))
    session.flush()


def _mk_worth(session, code: str, day: date, nav: float) -> None:
    from app.domains.funds.models import DailyWorth

    session.add(DailyWorth(fund_code=code, date=day, unit_nav=nav))
    session.flush()


def test_fund_type_id_of(provider, market_db):
    type_id = _mk_fund_type(market_db, '股票型')
    _mk_fund(market_db, '000001', type_id)
    assert provider.fund_type_id_of('000001') == type_id
    assert provider.fund_type_id_of('999999') is None


def test_peer_year_returns_includes_self_and_same_type_only(provider, market_db):
    """同类型 3 只（含自身）进集合，其它类型不进；窗口取最早/最晚净值。"""
    type_a = _mk_fund_type(market_db, '股票型')
    type_b = _mk_fund_type(market_db, '债券型')
    for code in ('000001', '000002', '000003'):
        _mk_fund(market_db, code, type_a)
    _mk_fund(market_db, '000004', type_b)  # 不同类型，应被排除

    # 窗口 as_of = D0+400，回看 365 天 → 起点 ≈ D0+35
    as_of = D0 + timedelta(days=400)
    _mk_worth(market_db, '000001', as_of - timedelta(days=300), 1.0)
    _mk_worth(market_db, '000001', as_of, 1.30)  # +30%
    _mk_worth(market_db, '000002', as_of - timedelta(days=200), 2.0)
    _mk_worth(market_db, '000002', as_of, 1.80)  # -10%
    _mk_worth(market_db, '000003', as_of - timedelta(days=100), 1.0)
    _mk_worth(market_db, '000003', as_of, 1.10)  # +10%
    _mk_worth(market_db, '000004', as_of - timedelta(days=100), 5.0)
    _mk_worth(market_db, '000004', as_of, 6.0)  # +20%，但不同类型

    peers = provider.peer_year_returns('000001', as_of)
    assert peers is not None
    assert len(peers) == 3  # 仅同类型 3 只
    assert pytest.approx(30.0) in [round(p, 4) for p in peers]
    assert pytest.approx(-10.0) in [round(p, 4) for p in peers]
    assert pytest.approx(10.0) in [round(p, 4) for p in peers]
    # 债券型那只（+20%）不在集合里
    assert not any(pytest.approx(20.0, abs=0.01) == p for p in peers)


def test_peer_year_returns_window_excludes_outside(provider, market_db):
    """窗口外的净值不参与（早于 as_of-365 的起点被忽略）。"""
    type_id = _mk_fund_type(market_db, '混合型')
    for code in ('000001', '000002'):
        _mk_fund(market_db, code, type_id)
    as_of = D0 + timedelta(days=400)
    # 000001：窗口外 0.5、窗口内 1.0 → 末日 1.2 → +20%（不起步于 0.5）
    _mk_worth(market_db, '000001', as_of - timedelta(days=500), 0.5)
    _mk_worth(market_db, '000001', as_of - timedelta(days=100), 1.0)
    _mk_worth(market_db, '000001', as_of, 1.2)
    _mk_worth(market_db, '000002', as_of - timedelta(days=100), 1.0)
    _mk_worth(market_db, '000002', as_of, 1.1)

    peers = provider.peer_year_returns('000001', as_of)
    assert peers is not None
    assert pytest.approx(20.0) in [round(p, 4) for p in peers]


def test_peer_year_returns_skips_funds_without_window_nav(provider, market_db):
    """窗口内无净值的同类基金不计入（宁缺勿假）。"""
    type_id = _mk_fund_type(market_db, 'QDII')
    for code in ('000001', '000002'):
        _mk_fund(market_db, code, type_id)
    as_of = D0 + timedelta(days=400)
    _mk_worth(market_db, '000001', as_of - timedelta(days=100), 1.0)
    _mk_worth(market_db, '000001', as_of, 1.1)
    _mk_worth(market_db, '000002', as_of - timedelta(days=800), 2.0)  # 窗口外

    peers = provider.peer_year_returns('000001', as_of)
    assert peers is not None
    assert len(peers) == 1  # 只有自身


def test_peer_year_returns_unknown_fund_returns_none(provider, market_db):
    """funds 表无此代码 → None（编排层按无同类数据降级）。"""
    assert provider.peer_year_returns('999999', D0) is None


def test_peer_year_returns_no_peers_with_type_returns_none(provider, market_db):
    """类型下只有自身、无其它基金时仍返回含自身的 1 元组（分位由 min_peers 降级）。"""
    type_id = _mk_fund_type(market_db, '商品型')
    _mk_fund(market_db, '000001', type_id)
    as_of = D0 + timedelta(days=400)
    _mk_worth(market_db, '000001', as_of - timedelta(days=100), 1.0)
    _mk_worth(market_db, '000001', as_of, 1.1)
    peers = provider.peer_year_returns('000001', as_of)
    assert peers is not None
    assert len(peers) == 1

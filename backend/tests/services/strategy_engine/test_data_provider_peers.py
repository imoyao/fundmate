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


# ── #2639：改写后的取数口径必须与旧实现逐值相等 ──


def _reference_peer_returns(session, type_id: int, as_of: date, window_days: int = 365):
    """旧实现的口径参照（把窗口内全部行拉进 Python 逐行求首末）。

    刻意**照抄修复前的算法**：本条测试的全部意义就是「优化没有改变口径」，
    参照实现若跟着新实现一起改，就成了自己给自己发合格证。
    """
    from app.domains.funds.models import DailyWorth, Fund

    codes = [r[0] for r in session.query(Fund.fund_code).filter(Fund.fund_type_id == type_id).all() if r[0]]
    if not codes:
        return None
    start = as_of - timedelta(days=window_days)
    rows = (
        session.query(DailyWorth.fund_code, DailyWorth.date, DailyWorth.unit_nav)
        .filter(
            DailyWorth.fund_code.in_(codes),
            DailyWorth.date >= start,
            DailyWorth.date <= as_of,
        )
        .order_by(DailyWorth.fund_code.asc(), DailyWorth.date.asc())
        .all()
    )
    firsts: dict[str, float] = {}
    lasts: dict[str, float] = {}
    for code, day, nav in rows:
        if day is None or nav is None:
            continue
        value = float(nav)
        if code not in firsts:
            firsts[code] = value
        lasts[code] = value
    return sorted((lasts[c] - firsts[c]) / firsts[c] * 100.0 for c in firsts if firsts[c] != 0 and c in lasts)


def test_peer_year_returns_matches_legacy_algorithm(provider, market_db):
    """多基金、多净值点、含窗口外点：新实现与旧算法输出逐值相等（#2639 判据）。"""
    type_id = _mk_fund_type(market_db, '股票型')
    as_of = D0 + timedelta(days=400)
    # 6 只同类，各 40 个净值点（覆盖窗口），起点都在窗口内不同位置
    for n, code in enumerate(('000001', '000002', '000003', '000004', '000005', '000006')):
        _mk_fund(market_db, code, type_id)
        base = 1.0 + n * 0.5
        _mk_worth(market_db, code, as_of - timedelta(days=500), base * 0.7)  # 窗口外，不应参与
        for i in range(40):
            _mk_worth(market_db, code, as_of - timedelta(days=300 - i * 6), base * (1.0 + i * 0.01))

    got = sorted(provider.peer_year_returns('000001', as_of))
    want = _reference_peer_returns(market_db, type_id, as_of)
    assert len(got) == len(want) == 6
    for a, b in zip(got, want):
        assert a == pytest.approx(b, abs=1e-9)


def test_peer_year_returns_cached_per_type_and_as_of(app, market_db):
    """同 (类型, 买入日) 只计算一次：命中缓存返回**同一个对象**（#2639 判据）。

    为什么用「对象身份」而不是数 SQL
        第一版用 `event.listen(engine, 'before_cursor_execute')` 数真实执行的语句，
        看起来更直接，但内存引擎在整个测试进程里共享，监听器会把别的会话的语句一起
        捕获进来 ⇒ 单独跑绿、整文件跑挂，随测试执行顺序漂移。一个会看运气的断言
        比没有断言更糟：它让人以为有保护。
        缓存命中必然返回缓存里的那个 `tuple` 实例，重建必然是新实例——
        `is` 判据确定、不依赖任何全局状态。附带断言值相等，避免「返回同一对象
        但内容是错的」。
    """
    from app.services.strategy_engine.data_provider import DataProvider

    type_id = _mk_fund_type(market_db, '混合型')
    as_of = D0 + timedelta(days=400)
    for code in ('000001', '000002'):
        _mk_fund(market_db, code, type_id)
        _mk_worth(market_db, code, as_of - timedelta(days=100), 1.0)
        _mk_worth(market_db, code, as_of, 1.1)

    provider = DataProvider(db=market_db, market_db=market_db)
    first = provider.peer_year_returns('000001', as_of)
    second = provider.peer_year_returns('000001', as_of)
    # 同类型、不同代码、同一买入日 → 复用同一份同类收益集合（缓存键是类型不是代码）
    third = provider.peer_year_returns('000002', as_of)
    # 不同买入日 → 不同键，必须重算
    other = provider.peer_year_returns('000001', as_of - timedelta(days=30))

    assert first is second, '同键二次调用应返回缓存对象（重建说明没有缓存）'
    assert first is third, '同类型同买入日的不同标的应共享同一份同类集合'
    assert first is not other, '不同买入日是不同的键，不得复用'
    assert first == second == third
    assert other != first


def test_peer_year_returns_null_nav_does_not_shift_boundary(market_db, app):
    """窗口首点净值缺失时，首末判定跳过该点（与旧口径一致，不得取到 NULL）。"""
    from sqlalchemy import text

    from app.services.strategy_engine.data_provider import DataProvider

    type_id = _mk_fund_type(market_db, 'QDII')
    _mk_fund(market_db, '000001', type_id)
    as_of = D0 + timedelta(days=400)
    # 直接写 NULL：`_mk_worth` 走 ORM 也行，但这里要钉的是「库里真有 NULL」这个前提
    market_db.execute(
        text(
            'insert into daily_worth (fund_code, date, unit_nav, created_at, updated_at) '
            "values ('000001', :d, null, datetime('now'), datetime('now'))"
        ),
        {'d': str(as_of - timedelta(days=300))},
    )
    market_db.flush()
    _mk_worth(market_db, '000001', as_of - timedelta(days=200), 1.0)
    _mk_worth(market_db, '000001', as_of, 1.2)

    peers = DataProvider(db=market_db, market_db=market_db).peer_year_returns('000001', as_of)
    assert peers is not None
    assert len(peers) == 1
    # 起点取 1.0（NULL 被跳过）→ +20%，而不是把 NULL 当起点
    assert peers[0] == pytest.approx(20.0)


def test_peer_year_returns_window_days_is_part_of_cache_key(provider, market_db):
    """缓存键含 window_days：不同窗口不得互相污染。"""
    type_id = _mk_fund_type(market_db, '指数型')
    _mk_fund(market_db, '000001', type_id)
    as_of = D0 + timedelta(days=400)
    _mk_worth(market_db, '000001', as_of - timedelta(days=300), 1.0)
    _mk_worth(market_db, '000001', as_of - timedelta(days=100), 1.5)
    _mk_worth(market_db, '000001', as_of, 1.2)

    long_window = provider.peer_year_returns('000001', as_of, window_days=365)
    short_window = provider.peer_year_returns('000001', as_of, window_days=150)
    # 365 天窗口：起点 1.0 → +20%；150 天窗口：起点 1.5 → -20%
    assert long_window[0] == pytest.approx(20.0)
    assert short_window[0] == pytest.approx(-20.0)

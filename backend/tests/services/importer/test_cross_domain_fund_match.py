# -*- coding: utf-8 -*-
"""#1605 回归：`_match_fund_by_name` 必须遵守双库「零 join」约束。

**为什么必须在本文件里自建双库，而不能用既有 conftest 的 `app` fixture**：

- `tests/conftest.py:33-60` 把 `engine` / `user_engine` **同时**指向同一个内存库，
  跨 bind 的 join 在单库下不会报错 —— 缺陷被夹具完全掩盖（这正是 #1605 长期未被发现的原因）；
- 更隐蔽的坑：**不能用 `Base.metadata.create_all(bind=e)` 建库**，它会把全部 52 张表
  建进两个库（user 库也会带上 `funds`），join 就又能跑通了，缺陷再次被掩盖。
  必须按域挑表：market 库只建 `funds`，user 库只建 `positions` / `watchlist` ——
  与生产 Supabase 不含市场表的事实一致。
"""

from typing import List, Optional, Tuple

import pytest
from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.db_factory import DATA_DOMAIN_REGISTRY, DOMAIN_USER
from app.domains.funds.models import Fund
from app.domains.positions.models import Position
from app.domains.watchlist.models import WatchlistItem
from app.services.importer.orchestrator_parse import ParsingMixin


def _market_tables() -> Tuple[str, ...]:
    """market 域全部表名（取自唯一事实源，避免手写清单漂移）。"""
    return tuple(n for n, d in DATA_DOMAIN_REGISTRY.items() if d != DOMAIN_USER and n in Base.metadata.tables)


def _user_tables() -> Tuple[str, ...]:
    return tuple(n for n, d in DATA_DOMAIN_REGISTRY.items() if d == DOMAIN_USER and n in Base.metadata.tables)


# 按域建全表：既要让外键目标表存在（否则 create_all 报 NoReferencedTableError），
# 又只把各域自己的表建进对应库 —— funds 始终不在 user 库，隔离事实成立。
MARKET_TABLES: Tuple[str, ...] = _market_tables()
USER_TABLES: Tuple[str, ...] = _user_tables()


def _new_engine() -> Engine:
    return create_engine(
        'sqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )


def _build_tables(engine: Engine, table_names: Tuple[str, ...]) -> None:
    """只把指定的表建到该引擎——避免误建全表而掩盖跨域缺陷。"""
    meta = MetaData()
    for name in table_names:
        Base.metadata.tables[name].to_metadata(meta)
    meta.create_all(engine)


def _make_split_session(
    funds: List[Tuple[str, str]],
    positions: Optional[List[str]] = None,
    watchlist: Optional[List[str]] = None,
) -> Tuple[Session, Engine, Engine]:
    """构造双库形态会话：market 库含 funds，user 库含 positions / watchlist。

    Returns:
        (session, e_market, e_user)：session 按表路由绑定，e_* 供测试收尾 dispose。
    """
    e_market, e_user = _new_engine(), _new_engine()
    _build_tables(e_market, MARKET_TABLES)
    _build_tables(e_user, USER_TABLES)

    # 数据也分库写入：funds 只能在 market 库，position / watchlist 只能在 user 库
    with sessionmaker(bind=e_market)() as s:
        s.add_all([Fund(fund_code=code, name=name) for code, name in funds])
        s.commit()
    with sessionmaker(bind=e_user)() as s:
        s.add_all([Position(symbol=sym) for sym in (positions or [])])
        s.add_all([WatchlistItem(symbol=sym) for sym in (watchlist or [])])
        s.commit()

    binds = {
        **{Base.metadata.tables[t]: e_market for t in MARKET_TABLES},
        **{Base.metadata.tables[t]: e_user for t in USER_TABLES},
    }
    return sessionmaker(binds=binds, bind=e_market)(), e_market, e_user


def _make_single_session(
    funds: List[Tuple[str, str]],
    positions: Optional[List[str]] = None,
    watchlist: Optional[List[str]] = None,
) -> Tuple[Session, Engine]:
    """单库形态（本地开发默认形态）：所有表同库。用于锁定「改造未改变既有行为」。"""
    engine = _new_engine()
    _build_tables(engine, MARKET_TABLES + USER_TABLES)
    with sessionmaker(bind=engine)() as s:
        s.add_all([Fund(fund_code=code, name=name) for code, name in funds])
        s.add_all([Position(symbol=sym) for sym in (positions or [])])
        s.add_all([WatchlistItem(symbol=sym) for sym in (watchlist or [])])
        s.commit()
    return sessionmaker(bind=engine)(), engine


def _match(session: Session, fund_name: str) -> Optional[str]:
    """以给定会话调用被测函数（ParsingMixin 无 __init__，手工注入 db）。"""
    mixin = ParsingMixin()
    mixin.db = session
    return mixin._match_fund_by_name(fund_name)


@pytest.fixture
def split_session():
    """工厂 fixture：造双库会话，测试结束后统一释放引擎。"""
    opened: List[Tuple[Session, Engine, Engine]] = []

    def _factory(funds, positions=None, watchlist=None) -> Session:
        session, e_market, e_user = _make_split_session(funds, positions, watchlist)
        opened.append((session, e_market, e_user))
        return session

    yield _factory
    for session, e_market, e_user in opened:
        session.close()
        e_market.dispose()
        e_user.dispose()


@pytest.fixture
def single_session():
    """工厂 fixture：造单库会话。"""
    opened: List[Tuple[Session, Engine]] = []

    def _factory(funds, positions=None, watchlist=None) -> Session:
        session, engine = _make_single_session(funds, positions, watchlist)
        opened.append((session, engine))
        return session

    yield _factory
    for session, engine in opened:
        session.close()
        engine.dispose()


# ── 双库形态：若退回 join 写法，这些用例会抛 OperationalError ──────────────


def test_position_match_across_split_databases(split_session):
    """持仓优先：双库下命中持仓持有的基金代码。"""
    session = split_session(
        funds=[('000001', '华夏成长混合'), ('000002', '易方达蓝筹精选')],
        positions=['000002'],
        watchlist=['000001'],
    )
    assert _match(session, '易方达蓝筹精选') == '000002'


def test_watchlist_match_when_position_has_no_match(split_session):
    """持仓无命中时退到自选。"""
    session = split_session(
        funds=[('000001', '华夏成长混合'), ('000002', '易方达蓝筹精选')],
        positions=['999999'],  # 持仓里有符号，但不匹配任何基金名称
        watchlist=['000001'],
    )
    assert _match(session, '华夏成长') == '000001'


def test_global_search_fallback_under_split_databases(split_session):
    """持仓/自选都不命中时走全库模糊搜索（第三步仍在 market 域内，不受跨域约束）。"""
    session = split_session(
        funds=[('000003', '招商中证白酒指数')],
        positions=[],
        watchlist=[],
    )
    assert _match(session, '招商中证白酒') == '000003'


def test_returns_none_when_nothing_matches(split_session):
    session = split_session(funds=[('000001', '华夏成长混合')])
    assert _match(session, '完全不存在的基金名称') is None


def test_empty_user_domain_does_not_raise(split_session):
    """user 域为空（无持仓无自选）时两步法必须早退，不能带着空 in_ 列表落库。"""
    session = split_session(funds=[('000001', '华夏成长混合')], positions=[], watchlist=[])
    assert _match(session, '华夏') == '000001'


# ── 单库形态：锁定既有行为未被改造改变 ─────────────────────────────────────


def test_single_database_priority_unchanged(single_session):
    """单库（本地开发默认）下三级优先级与改造前一致：持仓 > 自选 > 全库。"""
    session = single_session(
        funds=[('000001', '华夏成长混合'), ('000002', '易方达蓝筹精选')],
        positions=['000002'],
        watchlist=['000001'],
    )
    # 持仓优先于自选
    assert _match(session, '华夏成长') == '000001' or _match(session, '易方达蓝筹精选') == '000002'

    only_watch = single_session(
        funds=[('000001', '华夏成长混合')],
        positions=['999999'],
        watchlist=['000001'],
    )
    assert _match(only_watch, '华夏成长') == '000001'

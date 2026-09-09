# -*- coding: utf-8 -*-
"""跨域联合查询工具测试。

用两个内存 SQLite 模拟 market / user 双域，验证：
1. enrich_by_rows 通用两步法正确拼装（取 user 记录 → 批量取 market → 合并）。
2. enrich_watchlist_with_market 具体方法能把自选与市场资料按 (market, symbol) 关联。
3. user 侧无记录时返回空，不触发 market 查询。
"""

import pytest
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import sessionmaker

# 触发全部模型注册到 Base.metadata
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
from app.core.database import Base
from app.core.db_factory import (
    DOMAIN_MARKET,
    DOMAIN_USER,
    DatabaseFactory,
)
from app.services.cross_domain import CrossDomainQuery


def _build_split_engines():
    """按域在两个内存引擎分别建表，返回 (market_eng, user_eng)。"""
    grouped = DatabaseFactory.tables_by_domain(Base.metadata)
    market_eng = create_engine('sqlite:///:memory:')
    user_eng = create_engine('sqlite:///:memory:')
    for domain, eng in ((DOMAIN_MARKET, market_eng), (DOMAIN_USER, user_eng)):
        meta = MetaData()
        for t in grouped[domain]:
            t.to_metadata(meta)
        meta.create_all(bind=eng)
    return market_eng, user_eng


@pytest.fixture
def engines():
    return _build_split_engines()


def test_enrich_watchlist_with_market_joins_correctly(engines):
    market_eng, user_eng = engines
    market_sf = sessionmaker(bind=market_eng)
    user_sf = sessionmaker(bind=user_eng)

    # 准备 market 侧：一只基金 + 一只证券
    from app.domains.families.models import Family
    from app.domains.funds.models import Fund
    from app.domains.securities.models import Security
    from app.domains.watchlist.models import WatchlistItem

    with market_sf() as m:
        m.add(Fund(fund_code='000001', name='华夏成长'))
        m.add(Security(symbol='600000', name='浦发银行', market='SH', type='stock'))
        m.commit()

    with user_sf() as u:
        fam = Family(id=1, name='test')
        u.add(fam)
        u.add(WatchlistItem(family_id=1, symbol='000001', market='FUND'))
        u.add(WatchlistItem(family_id=1, symbol='600000', market='SH'))
        u.commit()

    cdq = CrossDomainQuery(user_sf, market_sf)
    result = cdq.enrich_watchlist_with_market(family_id=1)

    assert len(result) == 2
    by_symbol = {r['symbol']: r for r in result}
    assert by_symbol['000001']['market_data'].name == '华夏成长'
    assert by_symbol['600000']['market_data'].name == '浦发银行'


def test_enrich_returns_empty_when_no_user_rows(engines):
    market_eng, user_eng = engines
    cdq = CrossDomainQuery(sessionmaker(bind=user_eng), sessionmaker(bind=market_eng))
    # family_id=999 无自选
    assert cdq.enrich_watchlist_with_market(family_id=999) == []


def test_enrich_by_rows_generic_two_step(engines):
    """验证通用 enrich_by_rows 骨架可被任意 user→market 联合查询复用。"""
    market_eng, user_eng = engines
    market_sf = sessionmaker(bind=market_eng)
    user_sf = sessionmaker(bind=user_eng)

    from app.domains.families.models import Family
    from app.domains.funds.models import Fund
    from app.domains.watchlist.models import WatchlistItem

    with market_sf() as m:
        m.add(Fund(fund_code='000001', name='华夏成长'))
        m.commit()
    with user_sf() as u:
        u.add(Family(id=1, name='test'))
        u.add(WatchlistItem(family_id=1, symbol='000001', market='FUND'))
        u.commit()

    cdq = CrossDomainQuery(user_sf, market_sf)

    def user_provider(db):
        return db.query(WatchlistItem).all()

    def market_provider(db, keys):
        rows = db.query(Fund).filter(Fund.fund_code.in_([k[1] for k in keys])).all()
        return {(('FUND', r.fund_code)): r for r in rows}

    out = cdq.enrich_by_rows(
        user_rows_provider=user_provider,
        market_fetch=market_provider,
        join_key=lambda r: (r.market, r.symbol),
    )
    assert len(out) == 1
    assert out[0]['market_data'].name == '华夏成长'

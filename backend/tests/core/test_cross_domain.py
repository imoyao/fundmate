# -*- coding: utf-8 -*-
"""跨域联合查询工具测试。

用两个内存 SQLite 模拟 market / user 双域，验证：
1. enrich_by_rows 通用两步法正确拼装（取 user 记录 → 批量取 market → 合并）。
2. enrich_watchlist_with_market 具体方法能把自选与市场资料按 (market, symbol) 关联。
3. user 侧无记录时返回空，不触发 market 查询。
4. fetch_market_records_by_keys 只加载请求到的键、空 keys 不查库、且不得退化为全表扫描
   （#1404 回归护栏——修复前它忽略 keys、无条件 `query(Fund).all()`）。
"""

import pytest
from sqlalchemy import MetaData, create_engine, event
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
from app.services.cross_domain import CrossDomainQuery, fetch_market_records_by_keys


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


# ── fetch_market_records_by_keys：不得全表扫描（#1404）──


def _seed_market_with_noise(market_sf, requested=('000001',), noise=20):
    """播入 1 只「命中」基金 + N 只无关基金 + 2 只证券（含同名不同市场）。"""
    from app.domains.funds.models import Fund
    from app.domains.securities.models import Security

    with market_sf() as m:
        m.add_all([Fund(fund_code=c, name=f'命中{c}') for c in requested])
        m.add_all([Fund(fund_code=f'9{i:05d}', name=f'无关{i}') for i in range(noise)])
        m.add(Security(symbol='600000', name='浦发银行', market='SH', type='stock'))
        # 与基金代码 000001 同名，但属 SZ 命名空间——未请求就不该出现
        m.add(Security(symbol='000001', name='平安银行', market='SZ', type='stock'))
        m.commit()


def test_fetch_market_records_only_returns_requested_keys(engines):
    """只返回请求到的键（#1404 回归护栏）。

    此前实现忽略 keys、`db.query(Fund).all()` 无条件全表加载：自选列表每打开一次，
    就把全库约 2.7 万只基金 + 全部证券载入 ORM 实体。
    """
    market_eng, _user_eng = engines
    market_sf = sessionmaker(bind=market_eng)
    _seed_market_with_noise(market_sf)

    with market_sf() as db:
        got = fetch_market_records_by_keys(db, [('FUND', '000001'), ('SH', '600000')])

    assert set(got) == {('FUND', '000001'), ('SH', '600000')}
    assert got[('FUND', '000001')].name == '命中000001'
    assert got[('SH', '600000')].name == '浦发银行'


def test_fetch_market_records_empty_keys_returns_empty(engines):
    """空 keys → 空结果，且不应发起任何查询"""
    market_eng, _user_eng = engines
    market_sf = sessionmaker(bind=market_eng)

    with market_sf() as db:
        assert fetch_market_records_by_keys(db, []) == {}
        assert fetch_market_records_by_keys(db, set()) == {}


def test_fetch_market_records_issues_filtered_query(engines):
    """回归护栏：对 funds 的查询必须带 WHERE，不得退化为无条件全表扫描。"""
    market_eng, _user_eng = engines
    market_sf = sessionmaker(bind=market_eng)
    _seed_market_with_noise(market_sf)

    seen = []

    def _capture(_conn, _cursor, statement, _params, _ctx, _many):
        seen.append(' '.join(statement.split()))

    event.listen(market_eng, 'before_cursor_execute', _capture)
    try:
        with market_sf() as db:
            fetch_market_records_by_keys(db, [('FUND', '000001')])
    finally:
        event.remove(market_eng, 'before_cursor_execute', _capture)

    fund_stmts = [s for s in seen if 'FROM funds' in s]
    assert fund_stmts, '应当查询过 funds 表'
    assert all('WHERE' in s for s in fund_stmts), f'funds 查询带 WHERE 才不算全表扫描：{fund_stmts}'

    # 未请求 securities 时不应查 securities
    assert not [s for s in seen if 'FROM securities' in s]

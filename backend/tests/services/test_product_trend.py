# -*- coding: utf-8 -*-
"""产品历史走势取数（#1967 · 详情页走势区块）。

重点覆盖三件事：
1. 场内取**前复权**（``adj_close``）而非未复权 ``close``——除权日用 close 会画出一条假跳空；
2. 场外按**裸 6 位码**查 ``daily_worth``（入库侧没有 ``OF.`` 前缀）；
3. 无序列能力的品类（指数等）返回 ``None``，由端点降级成空序列而不是 404。
"""

from datetime import date, timedelta

import pytest

from app.domains.funds.models import DailyWorth, Fund
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.product_trend import fetch_product_trend

TREND_URL = '/api/products/trend/'


def _seed_price_series(db, symbol='SZ000001', points=5, adj_close=None, base_price=10.0):
    """造一段场内日线；``adj_close`` 为 None 时只写未复权 close。"""
    security = db.query(Security).filter(Security.symbol == symbol).first()
    if security is None:
        security = Security(symbol=symbol, name='测试证券', market='CN_A', type='stock')
        db.add(security)
        db.flush()
    start = date.today() - timedelta(days=points + 2)
    for i in range(points):
        db.add(
            PriceHistory(
                security_id=security.id,
                symbol=symbol,
                trade_date=start + timedelta(days=i),
                close=base_price + i,
                adj_close=adj_close,
            )
        )
    db.commit()


def _seed_nav_series(db, fund_code='004369', points=5):
    fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
    if fund is None:
        fund = Fund(fund_code=fund_code, name='测试基金')
        db.add(fund)
        db.flush()
    start = date.today() - timedelta(days=points + 2)
    for i in range(points):
        db.add(
            DailyWorth(
                fund_code=fund_code,
                date=start + timedelta(days=i),
                unit_nav=2.0 + i * 0.01,
            )
        )
    db.commit()


def test_close_series_prefers_adjusted_close(db):
    """有 adj_close 时必须用它——close 是未复权价，除权日会跳空。"""
    _seed_price_series(db, adj_close=9.5)

    result = fetch_product_trend(db, 'SZ000001', asset_type='stock', range_key='3M')

    assert result is not None
    assert result['kind'] == 'close'
    assert result['values'], '应有序列'
    # 每点都该是 adj_close=9.5，而不是 close=10.0, 11.0 ...
    assert set(result['values']) == {9.5}


def test_close_series_falls_back_to_close(db):
    """adj_close 缺失时回退 close（存量行可能没回填复权价）。"""
    _seed_price_series(db, adj_close=None)

    result = fetch_product_trend(db, 'SZ000001', asset_type='stock', range_key='1M')

    assert result is not None
    assert result['values'] == [10.0, 11.0, 12.0, 13.0, 14.0]


def test_fund_uses_unit_nav_by_bare_code(db):
    """场外基金按裸 6 位码查 daily_worth，kind=nav。"""
    _seed_nav_series(db, fund_code='004369')

    result = fetch_product_trend(db, '004369', asset_type='fund', range_key='3M')

    assert result is not None
    assert result['kind'] == 'nav'
    assert len(result['values']) == 5
    assert len(result['dates']) == len(result['values']), '日期轴与数值必须等长'


def test_index_has_no_series(db):
    """指数没有历史序列数据源 → None（不是空数组，由端点决定怎么降级）。"""
    assert fetch_product_trend(db, 'SH000300', asset_type='index', range_key='3M') is None


def test_invalid_range_raises(db):
    with pytest.raises(ValueError):
        fetch_product_trend(db, 'SZ000001', asset_type='stock', range_key='5Y')


def test_available_days_reflects_real_span(db):
    """available_days 反映实际跨度，供前端「无长历史自动收敛可用档」。"""
    _seed_price_series(db, points=5)

    result = fetch_product_trend(db, 'SZ000001', asset_type='stock', range_key='3M')

    assert result is not None
    assert result['requested_days'] == 90
    assert 0 < result['available_days'] < 90, '点数少时可用跨度应远小于请求的 90 天'


def test_endpoint_returns_empty_series_for_index(client, db):
    """端点对无序列品类返回 200 + 空序列（前端渲染空态），而不是 404。"""
    resp = client.get(TREND_URL, query_string={'symbol': 'SH000300', 'asset_type': 'index'})

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['dates'] == []
    assert data['values'] == []


def test_endpoint_invalid_range_returns_400(client, db):
    resp = client.get(TREND_URL, query_string={'symbol': 'SZ000001', 'range': '5Y'})

    assert resp.status_code == 400
    assert resp.get_json()['error_code'] == 1001  # ErrorCode.INVALID_PARAMS


def test_endpoint_default_range_is_3m(client, db):
    """设计 §12 ⑤：默认档 3M。"""
    _seed_price_series(db)

    resp = client.get(TREND_URL, query_string={'symbol': 'SZ000001', 'asset_type': 'stock'})

    assert resp.status_code == 200
    assert resp.get_json()['data']['range'] == '3M'

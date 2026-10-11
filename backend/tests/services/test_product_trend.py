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
                open=base_price + i - 0.5,
                high=base_price + i + 1,
                low=base_price + i - 1,
                close=base_price + i,
                adj_close=adj_close,
                volume=1000 + i,
                # 真实落库的场内来源码（akshare_adapter：股票走新浪、ETF 走东财）
                source='akshare_sina',
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


# ── 数据来源表述（#1969）──────────────────────────────────────────────
def test_source_is_site_name_not_internal_table(db):
    """出场的是**站点名**，不是内部表名。

    此前这里给的是 `'price_history 前复权收盘价'` —— 用户既看不懂 `price_history`，
    也看不出这根线到底来自哪个网站。口径信息改由 `basis` 单独承担。
    """
    _seed_price_series(db, points=5)

    result = fetch_product_trend(db, 'SZ000001', asset_type='stock', range_key='1M')

    assert result is not None
    assert result['source'] == '新浪财经'
    assert 'price_history' not in result['source']
    # 口径要说清「图上画的是未复权 K 线，而区间涨跌幅按前复权」——两者不同，
    # 不讲清楚用户会拿图上首尾差去核对涨跌幅（#1969）
    assert 'K 线' in result['basis'] and '前复权' in result['basis']


def test_fund_source_is_daily_fund_site(db):
    """场外基金净值来自天天基金（xalpha → pingzhongdata / lsjz）。"""
    _seed_nav_series(db, fund_code='004369')

    result = fetch_product_trend(db, '004369', asset_type='fund', range_key='3M')

    assert result is not None
    assert result['source'] == '天天基金'
    assert result['basis'] == '单位净值'


# ── K 线数据（#1969）──────────────────────────────────────────────────
def test_ohlc_is_exchange_only(db):
    """场内回未复权 OHLCV（画 K 线与成交量）；场外为空数组（改画净值线）。

    这条同时锁住「K 线用未复权」：与 `values`（前复权收盘价）**有意不同**——K 线要能跟
    持仓成本对账，前复权价对不上用户实际成交价。
    """
    _seed_price_series(db, points=5)

    result = fetch_product_trend(db, 'SZ000001', asset_type='stock', range_key='1M')

    assert result is not None
    assert len(result['ohlc']) == 5, '每个交易日一根 K 线'
    bar = result['ohlc'][0]
    assert bar['date'] == result['dates'][0]
    assert bar['close'] == 10.0
    assert bar['open'] == 9.5
    assert bar['high'] == 11.0
    assert bar['low'] == 9.0
    assert bar['volume'] == 1000


def test_ohlc_keeps_null_intraday_prices(db):
    """`open/high/low` 缺失时原样回 None——**不用收盘价编造盘中数据**（由前端降级绘制）。"""
    symbol = 'SZ000002'
    _seed_price_series(db, symbol=symbol, points=3)
    db.query(PriceHistory).filter(PriceHistory.symbol == symbol).update(
        {PriceHistory.open: None, PriceHistory.high: None, PriceHistory.low: None}
    )
    db.commit()

    result = fetch_product_trend(db, symbol, asset_type='stock', range_key='1M')

    assert result is not None
    assert result['ohlc'][0]['open'] is None
    assert result['ohlc'][0]['high'] is None
    assert result['ohlc'][0]['close'] == 10.0, '收盘价仍在，K 线才画得出来'


def test_ohlc_empty_for_fund(db):
    """场外基金没有 OHLC → 空数组，前端据此画净值线而不是 K 线。"""
    _seed_nav_series(db, fund_code='004369')

    result = fetch_product_trend(db, '004369', asset_type='fund', range_key='3M')

    assert result is not None
    assert result['ohlc'] == []


def test_endpoint_default_range_is_3m(client, db):
    """设计 §12 ⑤：默认档 3M。"""
    _seed_price_series(db)

    resp = client.get(TREND_URL, query_string={'symbol': 'SZ000001', 'asset_type': 'stock'})

    assert resp.status_code == 200
    assert resp.get_json()['data']['range'] == '3M'

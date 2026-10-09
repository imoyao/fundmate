# -*- coding: utf-8 -*-
"""股票资料聚合（#1969 · 详情页股票详情区块）。

重点覆盖四件事：
1. **窗口按交易日条数切**（不是自然日）——造 70 个交易日、把最老 10 天塞进异常高低，
   断言它们不参与统计：否则「近 60 日」在不同停牌密度的股票上口径会漂；
2. **收盘价优先前复权**（`adj_close`），但**区间高低用未复权原值**——两者口径不同，
   前者供区间涨跌幅，后者与持仓页「当日最高 / 最低」展示口径一致；
3. **没有行情不等于没涨**：无行情行时 `change_pct` 返回 `None` 而不是 0；
   无行情也不影响资料本身（只有证券不存在才 404）；
4. **资料缺失诚实降级为 `None`**（如 `sector`），由前端显示「—」，不编造占位值。

⚠️ 测试数据一律造在 **market 域**会话：`securities` / `price_history` 属 market 域，
生产下是独立引擎，端点与「读市场数据必须经 market_session_factory」的硬规则都要求如此。
"""

from contextlib import closing
from datetime import date, timedelta

import pytest

from app.core.db_factory import market_session_factory
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.stock_profile import DEFAULT_WINDOW, build_stock_profile

PROFILE_URL = '/api/products/stock-profile/'

# 造 70 个交易日、窗口取 60：最老的 10 天必须被裁掉，否则「区间高低」会被历史极值污染
_SEED_POINTS = 70
_DROPPED_POINTS = _SEED_POINTS - DEFAULT_WINDOW
_SPIKE_HIGH = 999.0
_SPIKE_LOW = 0.5


def _market_db():
    """market 域会话（securities / price_history 都在 market 域）。"""
    return market_session_factory()()


def _seed_security(symbol='SZ000001', name='平安银行', market='CN_A', sector='银行'):
    """确保证券存在并**已提交**，返回其 id（int，不是 ORM 实例）。

    两个容易踩的点：

    1. **必须 commit**，只 ``flush`` 不够——``closing`` 退出即关 session，未提交的写入
       会被回滚，随后插 ``price_history`` 就撞外键（``price_history.security_id`` 指向
       ``securities.id`` 且 NOT NULL）：``sqlite3.IntegrityError: FOREIGN KEY constraint failed``；
    2. **只回 id**：commit 后实例属性已过期（expire_on_commit），先取 id 再提交，避免
       session 关闭后取属性抛 DetachedInstanceError。

    已存在时**覆盖**各字段而非跳过：conftest 的 ``clean_db`` 只清当前会话引擎实际存在的
    表，market 域残留不保证被清，不覆盖会让上一个用例的 ``sector`` 串到下一个用例。
    """
    with closing(_market_db()) as db:
        security = db.query(Security).filter(Security.symbol == symbol).first()
        if security is None:
            security = Security(symbol=symbol, name=name, market=market, type='stock')
            db.add(security)
        security.name = name
        security.market = market
        security.type = 'stock'
        security.currency = 'CNY'
        security.sector = sector
        db.flush()
        security_id = security.id
        db.commit()
    return security_id


def _seed_prices(
    symbol='SZ000001',
    points=_SEED_POINTS,
    base_price=10.0,
    adj_offset=None,
    spike_oldest=False,
):
    """造一段场内日线（``trade_date`` 递增：第 0 条最老、末条最新）。

    Args:
        points: 交易日条数。
        base_price: 最老一天的 ``close``；第 i 天为 ``base_price + i``。
        adj_offset: 非 None 时写入 ``adj_close = close + adj_offset``（验证复权优先），
            为 None 则整列留空（验证回退 close）。
        spike_oldest: 把最老一天的高低设成极端值，供窗口裁剪断言。
    """
    with closing(_market_db()) as db:
        db.query(PriceHistory).filter(PriceHistory.symbol == symbol).delete()
        db.flush()
        security = db.query(Security).filter(Security.symbol == symbol).first()
        start = date.today() - timedelta(days=points - 1)
        rows = []
        for i in range(points):
            close = base_price + i
            high, low = close + 1, close - 1
            if spike_oldest and i == 0:
                high, low = _SPIKE_HIGH, _SPIKE_LOW
            rows.append(
                PriceHistory(
                    security_id=security.id,
                    symbol=symbol,
                    trade_date=start + timedelta(days=i),
                    close=close,
                    adj_close=base_price + i + adj_offset if adj_offset is not None else None,
                    high=high,
                    low=low,
                    # 真实落库的场内来源码，供「来源要出站点名」的断言用
                    source='akshare_sina',
                )
            )
        db.add_all(rows)
        db.commit()


def _expected_window_slice(points=_SEED_POINTS, base_price=10.0):
    """窗口内应参与统计的 close 列表（升序），与 ``_seed_prices`` 的造数规则同源。"""
    return [base_price + i for i in range(points - DEFAULT_WINDOW, points)]


# ── service 层 ────────────────────────────────────────────────────────
def test_window_counts_trading_days_not_calendar_days():
    """窗口按**交易日条数**切：70 条只取最近 60 条，最老的 10 条不进统计。

    造数把最老一天的高低设成极端值（high=999 / low=0.5）：若实现按自然日切窗口，
    这个极值就会落进区间高低，断言立刻暴露。
    """
    _seed_security()
    _seed_prices(points=_SEED_POINTS, spike_oldest=True)

    with closing(_market_db()) as db:
        profile = build_stock_profile(db, 'SZ000001')

    assert profile is not None
    assert profile['trading_days'] == DEFAULT_WINDOW
    assert profile['window_days'] == DEFAULT_WINDOW

    window_closes = _expected_window_slice()
    # 高低取自窗口内（未复权原值 close ± 1），不含被裁掉那天的 999 / 0.5
    assert profile['high'] == max(window_closes) + 1
    assert profile['low'] == min(window_closes) - 1
    # 最新收盘 = 窗口末条；区间涨跌幅以窗口首条为基
    assert profile['close'] == window_closes[-1]
    assert profile['change_pct'] == round(
        (window_closes[-1] - window_closes[0]) / window_closes[0] * 100, 2
    )
    assert profile['quote_date'] == (date.today()).isoformat()


def test_close_prefers_adjusted_but_high_low_stay_raw():
    """收盘价优先 `adj_close`（复权），区间高低仍用未复权原值——两者口径不同。

    若区间高低也改用复权价，除权日之后的「区间最高」会与行情页展示的最高价对不上。
    """
    _seed_security()
    _seed_prices(points=_SEED_POINTS, adj_offset=100.0)

    with closing(_market_db()) as db:
        profile = build_stock_profile(db, 'SZ000001')

    assert profile is not None
    assert profile['close'] == _expected_window_slice()[-1] + 100.0, '收盘应取 adj_close'
    assert profile['high'] == max(_expected_window_slice()) + 1, '高低应取未复权原值'
    assert profile['low'] == min(_expected_window_slice()) - 1


def test_close_falls_back_to_raw_close():
    """`adj_close` 缺失（存量行未回填复权价）时回退 `close`。"""
    _seed_security()
    _seed_prices(points=5, adj_offset=None)

    with closing(_market_db()) as db:
        profile = build_stock_profile(db, 'SZ000001')

    assert profile is not None
    assert profile['close'] == 14.0
    assert profile['trading_days'] == 5


def test_change_pct_is_none_without_quotes():
    """没有任何行情行 → 各行情字段为 None、条数为 0；**资料本身仍返回**。

    「这只股票我没行情数据」与「这只股票不存在」是两件事：前者退化成「—」，
    后者才 404。同时 `change_pct` 必须是 None 而不是 0——「没数据」不能被读成「没涨」。
    """
    _seed_security(symbol='SZ000002', name='万科A')
    _seed_prices(symbol='SZ000002', points=0)

    with closing(_market_db()) as db:
        profile = build_stock_profile(db, 'SZ000002')

    assert profile is not None
    assert profile['name'] == '万科A'
    assert profile['trading_days'] == 0
    for field in ('quote_date', 'close', 'high', 'low', 'change_pct'):
        assert profile[field] is None, f'{field} 应为 None 而不是占位值'


def test_change_pct_is_none_when_base_close_is_zero():
    """区间首日收盘为 0（脏数据）→ 涨跌幅为 None，而不是 ZeroDivisionError。"""
    _seed_security(symbol='SZ000003')
    _seed_prices(symbol='SZ000003', points=3, base_price=0.0)

    with closing(_market_db()) as db:
        profile = build_stock_profile(db, 'SZ000003')

    assert profile is not None
    assert profile['change_pct'] is None


def test_profile_returns_none_for_unknown_symbol():
    with closing(_market_db()) as db:
        assert build_stock_profile(db, 'SZ999999') is None


def test_blank_symbol_raises_value_error():
    """空 symbol 抛 ValueError（由端点转 400），而不是静默返回 None。"""
    with closing(_market_db()) as db:
        with pytest.raises(ValueError):
            build_stock_profile(db, '   ')


def test_market_filter_excludes_other_market():
    """`market` 参与过滤：同码跨市场时避免拿到另一市场的同名证券。"""
    _seed_security(symbol='00700.HK', name='腾讯控股', market='CN_HK')

    with closing(_market_db()) as db:
        assert build_stock_profile(db, '00700.HK', market='US') is None
        assert build_stock_profile(db, '00700.HK', market='CN_HK') is not None


def test_missing_sector_degrades_to_none():
    """行业字段缺失 → None（前端显示「—」），不为凑版面编造值。"""
    _seed_security(symbol='SZ000004', sector=None)

    with closing(_market_db()) as db:
        profile = build_stock_profile(db, 'SZ000004')

    assert profile is not None
    assert profile['sector'] is None


# ── 数据来源表述（#1969）──────────────────────────────────────────────
def test_quote_source_is_site_name():
    """区间行情的来源是**站点名**：库里存 `akshare_sina`，出场必须是「新浪财经」。

    详情页脚注此前写 `price_history 前复权收盘价`——表名对用户没有意义（#1969）。
    """
    _seed_security()
    _seed_prices(points=5)

    with closing(_market_db()) as db:
        profile = build_stock_profile(db, 'SZ000001')

    assert profile is not None
    assert profile['source'] == '新浪财经'
    assert profile['basis'] == '前复权收盘价 / 未复权高低'


def test_quote_source_is_blank_without_quotes():
    """没有行情行时来源为空串——前端据此不渲染来源脚注（而不是显示「数据来源：」空挂）。"""
    _seed_security(symbol='SZ000002', name='万科A')
    _seed_prices(symbol='SZ000002', points=0)

    with closing(_market_db()) as db:
        profile = build_stock_profile(db, 'SZ000002')

    assert profile is not None
    assert profile['source'] == ''


# ── 端点 ──────────────────────────────────────────────────────────────
def test_endpoint_returns_profile(client, db):
    _seed_security()
    _seed_prices(points=_SEED_POINTS, spike_oldest=True)

    resp = client.get(PROFILE_URL, query_string={'symbol': 'SZ000001'})

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['symbol'] == 'SZ000001'
    assert data['name'] == '平安银行'
    assert data['asset_type'] == 'stock'
    assert data['currency'] == 'CNY'
    assert data['trading_days'] == DEFAULT_WINDOW


def test_endpoint_returns_404_for_unknown_symbol(client, db):
    resp = client.get(PROFILE_URL, query_string={'symbol': 'SZ999999'})

    assert resp.status_code == 404
    assert resp.get_json()['error_code'] == 1002  # ErrorCode.RESOURCE_NOT_FOUND


def test_endpoint_missing_symbol_returns_422(client, db):
    """缺 symbol → 422（查询契约校验），与 §1967 `/trend/` 的入口约定一致。"""
    resp = client.get(PROFILE_URL)

    assert resp.status_code == 422
    assert resp.get_json()['error_code'] == 1001  # ErrorCode.INVALID_PARAMS


def test_endpoint_blank_symbol_returns_400(client, db):
    """空白 symbol 过得了 min_length，由 service 抛 ValueError → 400。"""
    resp = client.get(PROFILE_URL, query_string={'symbol': '   '})

    assert resp.status_code == 400
    assert resp.get_json()['error_code'] == 1001  # ErrorCode.INVALID_PARAMS

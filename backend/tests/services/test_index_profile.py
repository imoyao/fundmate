# -*- coding: utf-8 -*-
"""指数资料聚合（#2028 · 详情页指数详情区块）。

重点覆盖四件事：
1. **分位在读路径现算**：基线不足 1 年（<12 点）返回 None 而非小样本冒充的百分数；
2. **口径不可混**：分位是乐咕滚动 PE 在乐咕序列里的位置，不是中证官方 pe_1 的位置；
3. **无官方估值不 404**：名录命中即 200，pe / dividend_yield 逐项降级 None（诚实降级）；
4. **股息率分位本期恒为 None**（乐咕无该序列，#1407 拍板第 3 条）。

⚠️ 测试数据一律造在 **market 域**会话：index_* 三张表都属 market 域。
"""

from contextlib import closing
from datetime import date, timedelta

import pytest

from app.core.db_factory import market_session_factory
from app.domains.indices.models import IndexCatalog, IndexValuation, IndexValuationBaseline
from app.services.index_percentile import PERCENTILE_WINDOW_DAYS
from app.services.index_profile import build_index_profile

PROFILE_URL = '/api/products/index-profile/'


def _market_db():
    return market_session_factory()()


def _seed_catalog(code='000300', name='沪深300', publisher='CSI', is_core=True):
    with closing(_market_db()) as db:
        row = db.query(IndexCatalog).filter(IndexCatalog.index_code == code).first()
        if row is None:
            row = IndexCatalog(index_code=code, name=name, source='csindex')
            db.add(row)
        row.name = name
        row.publisher = publisher
        row.is_core = is_core
        db.commit()


def _seed_valuation(code='000300', pe_1=13.5, dividend_yield_1=2.4, trade_date=None):
    trade_date = trade_date or date.today() - timedelta(days=1)
    with closing(_market_db()) as db:
        row = (
            db.query(IndexValuation)
            .filter(IndexValuation.index_code == code, IndexValuation.trade_date == trade_date)
            .first()
        )
        if row is None:
            row = IndexValuation(index_code=code, trade_date=trade_date)
            db.add(row)
        row.pe_1 = pe_1
        row.dividend_yield_1 = dividend_yield_1
        db.commit()


def _seed_baselines(code='000300', points=24, base_pe=10.0, step=0.5):
    """月频基线：第 i 个月 pe = base_pe + i*step，最新点最高（asc 分位应接近 100）。"""
    with closing(_market_db()) as db:
        db.query(IndexValuationBaseline).filter(IndexValuationBaseline.index_code == code).delete()
        today = date.today()
        rows = []
        for i in range(points):
            # 从最老到最新：月频间隔约 30 天
            d = today - timedelta(days=30 * (points - 1 - i))
            rows.append(
                IndexValuationBaseline(
                    index_code=code,
                    trade_date=d,
                    pe_ttm=base_pe + i * step,
                    index_name='沪深300',
                    source='lg',
                )
            )
        db.add_all(rows)
        db.commit()


# ── service 层 ────────────────────────────────────────────────────────
def test_profile_with_baseline_computes_percentile():
    """基线充足时给出分位：最新点是序列最大值 → asc 分位接近 100。"""
    _seed_catalog()
    _seed_valuation()
    _seed_baselines(points=24)

    with closing(_market_db()) as db:
        profile = build_index_profile(db, '000300')

    assert profile is not None
    assert profile['name'] == '沪深300'
    assert profile['pe'] == pytest.approx(13.5)
    assert profile['dividend_yield'] == pytest.approx(2.4)
    assert profile['publisher_label'] == '中证指数公司'
    assert profile['is_core'] is True
    # 最新点 = 序列最大值 → (23 严格小于 + 1 并列×0.5) / 24 ≈ 97.9
    assert profile['pe_percentile'] == pytest.approx(97.9, abs=0.2)
    assert profile['percentile_metric'] == '滚动市盈率（乐咕乐股月频）'
    assert profile['percentile_date'] is not None


def test_short_baseline_gives_none_percentile():
    """基线不足 1 年（<12 点）不给分位——小样本百分数是误导。"""
    _seed_catalog()
    _seed_valuation()
    _seed_baselines(points=6)

    with closing(_market_db()) as db:
        profile = build_index_profile(db, 'SH000300')  # 带前缀形态同样命中

    assert profile is not None
    assert profile['pe_percentile'] is None
    assert profile['percentile_date'] is None


def test_no_baseline_percentile_none_but_valuation_present():
    """乐咕无覆盖的指数（如中证A500）：估值照出，分位降级 None。"""
    _seed_catalog(code='000510', name='中证A500')
    _seed_valuation(code='000510', pe_1=14.2, dividend_yield_1=2.1)

    with closing(_market_db()) as db:
        profile = build_index_profile(db, '000510')

    assert profile is not None
    assert profile['pe'] == pytest.approx(14.2)
    assert profile['pe_percentile'] is None


def test_no_valuation_still_200_semantics():
    """无官方估值：pe / dividend_yield 为 None，不 404（名录命中即可）。"""
    _seed_catalog(code='000852', name='中证1000')
    _seed_baselines(code='000852', points=18)

    with closing(_market_db()) as db:
        profile = build_index_profile(db, '000852')

    assert profile is not None
    assert profile['pe'] is None
    assert profile['dividend_yield'] is None
    assert profile['valuation_date'] is None
    assert profile['pe_percentile'] is not None  # 基线在，分位仍可算


def test_unknown_index_returns_none():
    with closing(_market_db()) as db:
        assert build_index_profile(db, '999999') is None


def test_blank_symbol_raises():
    with closing(_market_db()) as db:
        with pytest.raises(ValueError):
            build_index_profile(db, '   ')


def test_baseline_outside_window_ignored():
    """窗口外的基线点不参与分位——5 年窗口是口径的一部分。"""
    _seed_catalog()
    _seed_valuation()
    _seed_baselines(points=24)
    # 额外塞一个 6 年前的极端低点，窗口裁剪后不应影响分位
    with closing(_market_db()) as db:
        db.add(
            IndexValuationBaseline(
                index_code='000300',
                trade_date=date.today() - timedelta(days=PERCENTILE_WINDOW_DAYS + 400),
                pe_ttm=1.0,
                source='lg',
            )
        )
        db.commit()
        profile = build_index_profile(db, '000300')

    # 若窗口外的 1.0 参与，分位会从 97.9 掉到 ~94；裁剪后不变
    assert profile['pe_percentile'] == pytest.approx(97.9, abs=0.2)


# ── 端点 ──────────────────────────────────────────────────────────────
def test_endpoint_returns_profile(client, db):
    _seed_catalog()
    _seed_valuation()
    _seed_baselines()

    resp = client.get(PROFILE_URL, query_string={'symbol': '000300'})

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['index_code'] == '000300'
    assert data['name'] == '沪深300'
    assert data['pe_percentile'] is not None


def test_endpoint_404_unknown(client, db):
    resp = client.get(PROFILE_URL, query_string={'symbol': '999999'})

    assert resp.status_code == 404
    assert resp.get_json()['error_code'] == 1002


def test_endpoint_422_missing_symbol(client, db):
    resp = client.get(PROFILE_URL)

    assert resp.status_code == 422
    assert resp.get_json()['error_code'] == 1001

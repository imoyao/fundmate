# -*- coding: utf-8 -*-
"""指数详情页指标（#2278 · 阶段性收益 / 年化波动率 / 十大权重）。

重点覆盖六件事：
1. **窗口口径**：基期 = 「<= 目标日的最后一个交易日」（自然对齐交易日，节假日天然
   跳过）；今年至今基期 = 上一年最后一个交易日；历史不足窗口 → 该窗口 null 不编数；
2. **数据链路由**：中证官网优先（9 系唯一源），腾讯兜底必须带交易所后缀
   （裸码会把 000300 误路由成 sz——实测坑）；两路全空全字段 null；
3. **年化波动率**：日频简单收益样本标准差 × √252，历史不足 1 年 → null；
4. **TTL 缓存**：同码第二次构建零外部请求（含「两路全空」的负结果也进缓存）；
5. **权重聚合**：中文列名解析（实测 2026-10-17）、top10 降序、前十大集中度、
   成分码前导零防御（'591' → '000591'）、接口失败/空 df 整块降级；
6. **聚合测试一律不联网**：direct_feeds 两路与 akshare 全部 monkeypatch，
   缓存按用例注入 tmp_path 隔离（file_dir），today 固定为 2026-10-17 保证确定性。
"""

from contextlib import closing
from datetime import date, timedelta

import pandas as pd
import pytest

from app.core.cache import CacheService
from app.core.db_factory import market_session_factory
from app.domains.indices.models import IndexCatalog
from app.services import index_metrics as im
from app.services.index_metrics import (
    build_index_returns,
    build_index_weights,
    compute_period_returns,
    _shift_months,
)

FIXED_TODAY = date(2026, 10, 17)

RETURNS_URL = '/api/products/index-returns/'
WEIGHTS_URL = '/api/products/index-weights/'


class _FixedDate(date):
    """today() 固定的 date 子类：fromisoformat 等继承真实实现。"""

    @classmethod
    def today(cls) -> date:
        return FIXED_TODAY


def _series(start: date, end: date, daily_growth: float = 1.001) -> list:
    """自然日连续序列（含周末——合成数据只为窗口算术确定性）：closes 等比增长。"""
    days = (end - start).days + 1
    return [((start + timedelta(days=i)).isoformat(), round(1000.0 * daily_growth**i, 6)) for i in range(days)]


def _close_at(rows: list, day: date) -> float:
    for d, close in rows:
        if d == day.isoformat():
            return close
    raise AssertionError(f'series 里没有 {day}')


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """三重隔离：缓存注入 tmp_path、today 固定、外部源默认全空（具体用例再覆写）。"""
    monkeypatch.setattr(im, '_METRICS_CACHE', CacheService(namespace='test_index_metrics', file_dir=tmp_path))
    monkeypatch.setattr(im, 'date', _FixedDate)
    monkeypatch.setattr(im.direct_feeds, 'fetch_daily_csindex', lambda code, **k: [])
    monkeypatch.setattr(im.direct_feeds, 'fetch_daily_tencent', lambda symbol, **k: [])
    yield


def _seed_catalog_row(code='931151', name='光伏产业', exchange='CSI'):
    """名录种子：带 exchange（#1365 字段，路由腾讯兜底的后缀来源）。"""
    with closing(market_session_factory()()) as db:
        row = db.query(IndexCatalog).filter(IndexCatalog.index_code == code).first()
        if row is None:
            row = IndexCatalog(index_code=code, name=name, source='csindex')
            db.add(row)
        row.name = name
        row.exchange = exchange
        db.commit()


# ── 阶段性收益：窗口算术 ──────────────────────────────────────────────
def test_returns_all_windows_computed(monkeypatch):
    """4 年自然日序列：六窗口全部有值，m1/ytd 与手算一致，等比序列波动率为 0。"""
    _seed_catalog_row()
    rows = _series(date(2022, 8, 1), date(2026, 10, 16))
    calls = []

    def _fake_csindex(code, **k):
        calls.append(('csindex', code))
        return rows

    monkeypatch.setattr(im.direct_feeds, 'fetch_daily_csindex', _fake_csindex)

    with closing(market_session_factory()()) as db:
        data = build_index_returns(db, '931151')

    assert calls == [('csindex', '931151')]  # 中证官网优先且只打这一路
    assert data['as_of'] == '2026-10-16'
    assert data['source'] == 'csindex'

    latest = rows[-1][1]
    base_m1 = _close_at(rows, FIXED_TODAY - timedelta(days=30))
    assert data['returns']['m1'] == round((latest / base_m1 - 1) * 100, 2)
    base_ytd = _close_at(rows, date(2025, 12, 31))
    assert data['returns']['ytd'] == round((latest / base_ytd - 1) * 100, 2)
    # 严格递增序列：窗口越长收益越大；等比日收益 → 样本标准差 0 → 年化波动率 0.0
    assert data['returns']['y1'] is not None
    assert data['returns']['y2'] > data['returns']['y1']
    assert data['returns']['y3'] > data['returns']['y2']
    assert data['volatility_y1'] == 0.0


def test_returns_short_history_nulls(monkeypatch):
    """仅 1 个多月历史：m3/ytd/y1-y3 全 null（窗口不足）；m1 可算；
    波动率样本 ≥20 → 可算（几何序列为 0.0，非 None）。"""
    _seed_catalog_row()
    rows = _series(date(2026, 9, 1), date(2026, 10, 16))
    monkeypatch.setattr(im.direct_feeds, 'fetch_daily_csindex', lambda code, **k: rows)

    with closing(market_session_factory()()) as db:
        data = build_index_returns(db, '931151')

    latest, base_m1 = rows[-1][1], _close_at(rows, FIXED_TODAY - timedelta(days=30))
    assert data['returns']['m1'] == round((latest / base_m1 - 1) * 100, 2)
    assert data['returns']['m3'] is None
    assert data['returns']['ytd'] is None  # 序列全部在本年内，无上年末基期
    assert data['returns']['y1'] is None
    assert data['returns']['y2'] is None
    assert data['returns']['y3'] is None
    # ~45 个日收益 ≥ 20 → 年化波动率可算（几何序列 = 0.0），不是 None
    assert data['volatility_y1'] == 0.0


def test_returns_tencent_fallback_with_exchange_suffix(monkeypatch):
    """中证官网空 → 腾讯兜底；名录带 exchange 时必须拼后缀（000300 是沪市，裸码会误路由）。"""
    _seed_catalog_row(code='000300', name='沪深300', exchange='SH')
    calls = []
    rows = _series(date(2025, 1, 1), date(2026, 10, 16))

    def _fake_tencent(symbol, **k):
        calls.append(symbol)
        return rows

    monkeypatch.setattr(im.direct_feeds, 'fetch_daily_tencent', _fake_tencent)

    with closing(market_session_factory()()) as db:
        data = build_index_returns(db, '000300')

    assert calls == ['000300.SH']
    assert data['source'] == 'tencent'
    assert data['returns']['y1'] is not None


def test_returns_both_sources_empty_degrades_and_negatively_cached(monkeypatch):
    """两路全空：200 语义的全 null 形态，且负结果进缓存（第二次零外部请求）。"""
    _seed_catalog_row()
    calls = []

    def _csindex(code, **k):
        calls.append('csindex')
        return []

    def _tencent(symbol, **k):
        calls.append(f'tencent:{symbol}')
        return []

    monkeypatch.setattr(im.direct_feeds, 'fetch_daily_csindex', _csindex)
    monkeypatch.setattr(im.direct_feeds, 'fetch_daily_tencent', _tencent)

    with closing(market_session_factory()()) as db:
        first = build_index_returns(db, '931151')
        second = build_index_returns(db, '931151')

    assert first == {
        'index_code': '931151',
        'as_of': None,
        'source': None,
        'returns': {'m1': None, 'm3': None, 'ytd': None, 'y1': None, 'y2': None, 'y3': None},
        'volatility_y1': None,
    }
    assert first == second
    assert len(calls) == 2  # csindex + tencent 各一次，第二次构建零请求


def test_returns_cached_across_builds(monkeypatch):
    """缓存命中：同码两次构建只拉一次数据（带前缀形态同码 → 命中同一缓存键）。"""
    _seed_catalog_row()
    rows = _series(date(2025, 1, 1), date(2026, 10, 16))
    calls = []

    def _csindex(code, **k):
        calls.append(code)
        return rows

    monkeypatch.setattr(im.direct_feeds, 'fetch_daily_csindex', _csindex)

    with closing(market_session_factory()()) as db:
        build_index_returns(db, '931151')
        build_index_returns(db, 'SH931151')

    assert len(calls) == 1


def test_unknown_index_returns_none():
    with closing(market_session_factory()()) as db:
        assert build_index_returns(db, '999999') is None
        assert build_index_weights(db, '999999') is None


def test_blank_symbol_raises():
    with closing(market_session_factory()()) as db:
        with pytest.raises(ValueError):
            build_index_returns(db, '   ')


# ── 十大权重 ──────────────────────────────────────────────────────────
def _weights_df(n: int = 12, weight_col='权重', trade_date='2026-09-30') -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            {
                '日期': trade_date,
                '指数代码': '931151',
                '指数名称': '光伏产业',
                '成分券代码': str(600000 + i),
                '成分券名称': f'成分股{i}',
                '交易所': '上海证券交易所',
                weight_col: round(10.0 - i * 0.5, 3),  # 严格递减：首位 10.0
            }
        )
    return pd.DataFrame(rows)


def _patch_akshare(monkeypatch, df=None, exc=None):
    class _FakeAk:
        @staticmethod
        def index_stock_cons_weight_csindex(symbol: str):
            if exc is not None:
                raise exc
            return df

    monkeypatch.setattr('app.core.akshare_lazy.get_akshare', lambda: _FakeAk())


def test_weights_top10_shape_and_concentration(monkeypatch):
    """top10 降序切片 + 集中度/总数/合计正确；成分码前导零防御（'591' → '000591'）。"""
    _seed_catalog_row()
    df = _weights_df(n=12)
    df.loc[0, '成分券代码'] = '591'  # 模拟 pandas 吃掉前导零
    _patch_akshare(monkeypatch, df=df)

    with closing(market_session_factory()()) as db:
        data = build_index_weights(db, '931151')

    assert data['as_of'] == '2026-09-30'
    assert data['frequency'] == 'monthly'
    assert data['constituent_count'] == 12
    assert data['total_weight'] == round(sum(10.0 - i * 0.5 for i in range(12)), 2)
    assert len(data['top10']) == 10
    weights = [row['weight'] for row in data['top10']]
    assert weights == sorted(weights, reverse=True)
    assert data['top10'][0]['code'] == '000591'  # 前导零已补齐
    assert data['top10'][0]['weight'] == 10.0
    assert data['top10_weight'] == round(sum(10.0 - i * 0.5 for i in range(10)), 2)


def test_weights_degrade_on_error_and_empty(monkeypatch):
    """接口抛异常 / 空 df → 统一空形态，不抛出阻断详情页。"""
    _seed_catalog_row()

    _patch_akshare(monkeypatch, exc=RuntimeError('network down'))
    with closing(market_session_factory()()) as db:
        assert build_index_weights(db, '931151')['top10'] == []

    _patch_akshare(monkeypatch, df=pd.DataFrame())
    with closing(market_session_factory()()) as db:
        data = build_index_weights(db, '931151')
    assert data['top10'] == []
    assert data['top10_weight'] is None
    assert data['as_of'] is None


def test_weights_cached(monkeypatch):
    """月频数据 TTL 24h：同码两次构建只调一次 akshare。"""
    _seed_catalog_row()
    calls = []

    class _FakeAk:
        @staticmethod
        def index_stock_cons_weight_csindex(symbol: str):
            calls.append(symbol)
            return _weights_df(n=12)

    monkeypatch.setattr('app.core.akshare_lazy.get_akshare', lambda: _FakeAk())

    with closing(market_session_factory()()) as db:
        build_index_weights(db, '931151')
        build_index_weights(db, '931151')

    assert len(calls) == 1


# ── 端点契约 ──────────────────────────────────────────────────────────
def test_endpoint_returns_ok(client, db, monkeypatch):
    _seed_catalog_row()
    rows = _series(date(2025, 1, 1), date(2026, 10, 16))
    monkeypatch.setattr(im.direct_feeds, 'fetch_daily_csindex', lambda code, **k: rows)

    resp = client.get(RETURNS_URL, query_string={'symbol': '931151'})

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['index_code'] == '931151'
    assert data['returns']['ytd'] is not None


def test_endpoint_weights_ok(client, db, monkeypatch):
    _seed_catalog_row()
    _patch_akshare(monkeypatch, df=_weights_df(n=12))

    resp = client.get(WEIGHTS_URL, query_string={'symbol': 'SH931151'})

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['constituent_count'] == 12
    assert len(data['top10']) == 10


def test_endpoint_404_unknown(client, db):
    resp = client.get(RETURNS_URL, query_string={'symbol': '999999'})

    assert resp.status_code == 404
    assert resp.get_json()['error_code'] == 1002


def test_endpoint_422_missing_symbol(client, db):
    for url in (RETURNS_URL, WEIGHTS_URL):
        resp = client.get(url)

        assert resp.status_code == 422
        assert resp.get_json()['error_code'] == 1001


# ── 纯函数单测（合并 B 的自然月口径确定性用例；键名适配 A 的 returns / volatility_y1）──
def test_shift_months_month_end_clamps():
    """月末钳位：03-31 回 1 月 → 02-28（2026 平年）/ 02-29（2024 闰年），不越界。"""
    assert _shift_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert _shift_months(date(2024, 3, 31), -1) == date(2024, 2, 29)
    assert _shift_months(date(2026, 1, 15), -12) == date(2025, 1, 15)
    assert _shift_months(date(2026, 3, 15), -3) == date(2025, 12, 15)
    assert _shift_months(date(2026, 3, 15), -36) == date(2023, 3, 15)


def test_shift_months_across_year_boundary():
    assert _shift_months(date(2026, 1, 10), -1) == date(2025, 12, 10)
    assert _shift_months(date(2026, 1, 31), -1) == date(2025, 12, 31)


# 锚点稀疏但覆盖 3 年的序列：各窗口基准收盘已知 → 期望收益率手算可验。
_FULL = [
    ('2023-06-14', 60.0),
    ('2024-06-14', 70.0),
    ('2025-06-13', 80.0),
    ('2025-12-31', 85.0),
    ('2026-03-14', 90.0),
    ('2026-05-14', 100.0),
    ('2026-06-15', 110.0),
]
_TODAY = date(2026, 6, 15)


def test_compute_windows_full_history():
    """7 点锚点序列：6 窗口全部可算，逐个核对手算值（%）；1y 窗口样本 < 20 → 波动率 None。"""
    result = compute_period_returns(_FULL, today=_TODAY)
    assert result is not None
    assert result['as_of'] == '2026-06-15'
    w = result['returns']
    # 后端 _ret 已 round(..., 2)，与前端 toFixed(2) 口径一致
    assert w['m1'] == pytest.approx(10.0, abs=1e-9)
    assert w['m3'] == pytest.approx(22.22, abs=1e-9)
    assert w['ytd'] == pytest.approx(29.41, abs=1e-9)
    assert w['y1'] == pytest.approx(37.5, abs=1e-9)
    assert w['y2'] == pytest.approx(57.14, abs=1e-9)
    assert w['y3'] == pytest.approx(83.33, abs=1e-9)
    # 7 点 → 1y 窗口内仅 3 个日收益 < 20 → 波动率诚实降级
    assert result['volatility_y1'] is None


def test_compute_insufficient_history_windows_none():
    """今年才成立的序列：1m/3m 有基准可算，1y/2y/3y 与 ytd 全 None（不编数）。"""
    series = [
        ('2026-01-20', 100.0),
        ('2026-05-20', 105.0),
        ('2026-06-15', 110.0),
    ]
    result = compute_period_returns(series, today=_TODAY)
    assert result is not None
    w = result['returns']
    assert w['ytd'] is None  # 无上年末交易日
    assert w['y1'] is None
    assert w['y2'] is None
    assert w['y3'] is None
    assert w['m1'] == pytest.approx((110 / 100 - 1) * 100, abs=1e-9)
    assert w['m3'] == pytest.approx((110 / 100 - 1) * 100, abs=1e-9)


def test_compute_too_short_series_none():
    """单点 / 空序列算不出任何收益 → None（整块降级）。"""
    assert compute_period_returns([('2026-06-15', 100.0)], today=_TODAY) is None
    assert compute_period_returns([], today=_TODAY) is None


def test_compute_bad_latest_close_none():
    """最新收盘 ≤ 0（脏数据）→ None，不用它当分母。"""
    assert compute_period_returns([('2026-06-14', 100.0), ('2026-06-15', 0.0)], today=_TODAY) is None


def test_compute_unsorted_input_handled_by_baseline():
    """防御性排序：乱序输入仍给出与升序一致的正确 1y（锚定 today）。"""
    result = compute_period_returns(sorted(_FULL, reverse=True), today=_TODAY)
    assert result is not None
    assert result['returns']['y1'] == pytest.approx(37.5, abs=1e-9)


def test_volatility_constant_series_zero():
    """常数序列：日收益全 0 → 年化波动率 0.0（真实语义，不是缺数）。"""
    series = [(f'2026-{m:02d}-{d:02d}', 100.0) for m, d in [(1, i) for i in range(1, 29)]]
    # 2026-01-01..2026-01-28 共 28 点 → 27 个日收益 ≥ 20（整体落在近 1 年内）
    result = compute_period_returns(series, today=date(2026, 1, 28))
    assert result is not None
    assert result['volatility_y1'] == pytest.approx(0.0, abs=1e-12)


def test_volatility_too_few_samples_none():
    """日收益样本 < 20 → None（样本太小的波动率没意义）。"""
    series = [(f'2026-01-{i:02d}', 100.0 + i) for i in range(1, 15)]  # 14 点 → 13 收益
    result = compute_period_returns(series, today=date(2026, 1, 14))
    assert result is not None
    assert result['volatility_y1'] is None


def test_volatility_positive_for_varying_series():
    """跨 >1 年的工作日序列（有波动）→ 年化波动率 > 0（数量级合理）。"""
    rows = []
    d = date(2024, 1, 1)
    close = 100.0
    while d <= date(2026, 6, 15):
        if d.weekday() < 5:  # 仅工作日模拟交易日
            close *= 1.01 if (d.day % 2 == 0) else 0.99
            rows.append((d.isoformat(), round(close, 4)))
        d += timedelta(days=1)
    result = compute_period_returns(rows, today=date(2026, 6, 15))
    assert result is not None
    vol = result['volatility_y1']
    assert vol is not None and vol > 0

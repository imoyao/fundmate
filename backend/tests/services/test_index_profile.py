# -*- coding: utf-8 -*-
"""指数资料聚合（#2028 · 详情页指数详情区块）。

重点覆盖四件事：
1. **分位在读路径现算**：基线不足 1 年（<12 点）返回 None 而非小样本冒充的百分数；
2. **口径不可混**：分位是乐咕滚动 PE 在乐咕序列里的位置，不是中证官方 pe_1 的位置；
3. **无官方估值不 404**：名录命中即 200，pe / dividend_yield 逐项降级 None（诚实降级）；
4. **股息率分位本期恒为 None**（乐咕无该序列，#1407 拍板第 3 条）；
5. **简介按需抓取 + 进程内缓存**：中证官网未收录码族直接 None，网络故障不进缓存
   （下次可重试），正/负结果都缓存——聚合测试一律不联网（autouse 阻断）；
6. **#2278 三块独立降级**：快照字段（basic-info 同请求）/ 阶段性收益 / 十大权重
   各自 try/except，任一外部源异常只影响本块，不拖垮资料/估值首屏。

⚠️ 测试数据一律造在 **market 域**会话：index_* 三张表都属 market 域。
"""

from contextlib import closing
from datetime import date, timedelta

import pytest

from app.core.db_factory import market_session_factory
from app.domains.indices.models import IndexCatalog, IndexValuation, IndexValuationBaseline
from app.services import index_profile as ip
from app.services.index_percentile import PERCENTILE_WINDOW_DAYS
from app.services.index_profile import build_index_profile
from app.services.index_profile import fetch_csi_index_desc as _real_fetch_csi_desc
from app.services.index_profile import fetch_csi_snapshot as _real_fetch_csi_snapshot

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


@pytest.fixture(autouse=True)
def _no_external_network(monkeypatch):
    """本文件默认阻断全部外部抓取（聚合测试不联网）：四个 fetcher 换 None 实现并清缓存。

    直测 ``fetch_csi_index_desc`` / ``fetch_csi_snapshot`` 的用例自行把真实实现
    换回来（``_real_fetch_csi_desc`` / ``_real_fetch_csi_snapshot``）。basic-info
    缓存是模块级 dict，进出各清一次防跨用例污染。
    """
    monkeypatch.setattr(ip, 'fetch_csi_index_desc', lambda code: None)
    monkeypatch.setattr(ip, 'fetch_csi_snapshot', lambda code: None)
    monkeypatch.setattr(ip, 'fetch_period_returns', lambda code: None)
    monkeypatch.setattr(ip, 'fetch_top_weights', lambda code: None)
    ip._csi_basic_cache.clear()
    yield
    ip._csi_basic_cache.clear()


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


# ── 指数简介（中证官网 indexCnDesc：按需抓取 + 缓存 + 降级）─────────────
def test_profile_description_passthrough(monkeypatch):
    """简介走 fetch 注入：命中即原样进 profile。"""
    _seed_catalog()
    monkeypatch.setattr(ip, 'fetch_csi_index_desc', lambda code: '测试简介')

    with closing(_market_db()) as db:
        profile = build_index_profile(db, '000300')

    assert profile['description'] == '测试简介'


def test_profile_description_degrades_none():
    """官网未收录 / 抓取失败 → description=None（前端整段隐藏，不显「—」）。"""
    _seed_catalog()

    with closing(_market_db()) as db:
        profile = build_index_profile(db, '000300')

    assert profile['description'] is None


def test_fetch_csi_desc_caches_positive_and_gates(monkeypatch):
    """正结果进缓存（同码第二次不再发请求）；非覆盖码族直接降级且不发请求。"""
    monkeypatch.setattr(ip, 'fetch_csi_index_desc', _real_fetch_csi_desc)
    calls = []

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {'data': {'indexCnDesc': 'ABC'}}

    def _fake_get(url, timeout=None):
        calls.append(url)
        return _FakeResp()

    monkeypatch.setattr(ip.requests, 'get', _fake_get)

    assert ip.fetch_csi_index_desc('931151') == 'ABC'
    assert ip.fetch_csi_index_desc('931151') == 'ABC'
    assert len(calls) == 1  # 第二次命中进程内缓存
    assert ip.fetch_csi_index_desc('399001') is None  # 非覆盖码族：直接降级
    assert len(calls) == 1  # 且不发注定扑空的请求


def test_fetch_csi_desc_negative_cached(monkeypatch):
    """官网确认无简介（data 空）也进缓存：负结果不重复请求。"""
    monkeypatch.setattr(ip, 'fetch_csi_index_desc', _real_fetch_csi_desc)
    calls = []

    class _EmptyResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {'data': None}

    def _fake_get(url, timeout=None):
        calls.append(url)
        return _EmptyResp()

    monkeypatch.setattr(ip.requests, 'get', _fake_get)

    assert ip.fetch_csi_index_desc('931151') is None
    assert ip.fetch_csi_index_desc('931151') is None
    assert len(calls) == 1


def test_fetch_csi_desc_network_error_not_cached(monkeypatch):
    """瞬时网络故障 → None 但**不进缓存**：下次查看要重试，不把故障焊死。"""
    monkeypatch.setattr(ip, 'fetch_csi_index_desc', _real_fetch_csi_desc)
    calls = []

    def _boom(url, timeout=None):
        calls.append(url)
        raise RuntimeError('network down')

    monkeypatch.setattr(ip.requests, 'get', _boom)

    assert ip.fetch_csi_index_desc('931151') is None
    assert ip.fetch_csi_index_desc('931151') is None
    assert len(calls) == 2  # 两次都真的尝试了请求


# ── #2278 快照字段（basic-info 同请求顺手取）────────────────────────────
def test_fetch_csi_snapshot_shares_desc_request_cache(monkeypatch):
    """快照与简介共用一次 basic-info 请求：先取简介再取快照只发一个 HTTP。"""
    monkeypatch.setattr(ip, 'fetch_csi_snapshot', _real_fetch_csi_snapshot)
    calls = []

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                'data': {
                    'indexCnDesc': 'ABC',
                    'publishDate': '2019-04-22',
                    'consNumber': 50,
                    'weightingType': '自由加权',
                    'currencyCn': '人民币',
                }
            }

    def _fake_get(url, timeout=None):
        calls.append(url)
        return _FakeResp()

    monkeypatch.setattr(ip.requests, 'get', _fake_get)

    assert _real_fetch_csi_desc('931151') == 'ABC'  # 第一发：简介建立缓存
    snap = ip.fetch_csi_snapshot('931151')  # 第二发：命中同一缓存
    assert snap == {
        'publish_date': '2019-04-22',
        'cons_number': 50,
        'weighting_type': '自由加权',
        'currency': '人民币',
    }
    assert len(calls) == 1  # 关键：快照不另发请求


def test_fetch_csi_snapshot_degrades_none():
    """data 缺失（未收录 / 确认无数据）→ None，前端整块「—」。"""
    assert _real_fetch_csi_snapshot('399001') is None  # 非覆盖码族不发请求
    assert _real_fetch_csi_snapshot('  ') is None


def test_profile_snapshot_fields_present():
    """快照字段进 profile（fixture 已阻断 → None，键必须存在供前端判空）。"""
    _seed_catalog()

    with closing(_market_db()) as db:
        profile = build_index_profile(db, '000300')

    assert profile['publish_date'] is None
    assert profile['cons_number'] is None
    assert profile['weighting_type'] is None
    assert profile['currency'] is None


def test_profile_snapshot_fields_passthrough(monkeypatch):
    """快照字段注入即透传（平铺进 profile，前端并入 facts 行）。"""
    _seed_catalog()
    monkeypatch.setattr(
        ip,
        'fetch_csi_snapshot',
        lambda code: {
            'publish_date': '2005-04-08',
            'cons_number': 300,
            'weighting_type': '派济加权',
            'currency': '人民币',
        },
    )

    with closing(_market_db()) as db:
        profile = build_index_profile(db, '000300')

    assert profile['publish_date'] == '2005-04-08'
    assert profile['cons_number'] == 300
    assert profile['weighting_type'] == '派济加权'
    assert profile['currency'] == '人民币'


# ── #2278 阶段性收益 + 十大权重（外部源独立降级）────────────────────────
def test_profile_period_returns_and_weights_passthrough(monkeypatch):
    """两块注入即透传；结构原样进响应（服务端已折算为 %）。"""
    _seed_catalog()
    fake_returns = {
        'as_of': '2026-10-16',
        'windows': {'1m': 2.5, '3m': None, 'ytd': 12.0, '1y': 8.8, '2y': None, '3y': None},
        'volatility_1y': 18.2,
    }
    fake_weights = {
        'as_of': '2026-09-30',
        'rows': [{'symbol': '600519', 'name': '贵州茅台', 'weight': 9.218}],
        'top_sum': 52.101,
        'total_count': 50,
    }
    monkeypatch.setattr(ip, 'fetch_period_returns', lambda code: fake_returns)
    monkeypatch.setattr(ip, 'fetch_top_weights', lambda code: fake_weights)

    with closing(_market_db()) as db:
        profile = build_index_profile(db, '000300')

    assert profile['period_returns'] == fake_returns
    assert profile['top_weights'] == fake_weights


def test_profile_blocks_degrade_independently(monkeypatch):
    """收益块抛异常不影响权重块与资料首屏（互不拖垮是验收硬项）。"""
    _seed_catalog()
    _seed_valuation()

    def _boom(code):
        raise RuntimeError('csindex down')

    monkeypatch.setattr(ip, 'fetch_period_returns', _boom)
    monkeypatch.setattr(
        ip,
        'fetch_top_weights',
        lambda code: {'as_of': '2026-09-30', 'rows': [], 'top_sum': 0.0, 'total_count': 0},
    )

    with closing(_market_db()) as db:
        profile = build_index_profile(db, '000300')

    assert profile is not None
    assert profile['period_returns'] is None  # 本块降级
    assert profile['top_weights'] is not None  # 邻块不受影响
    assert profile['pe'] == pytest.approx(13.5)  # 资料首屏不受影响


def test_profile_weights_failure_does_not_block_returns(monkeypatch):
    """反向：权重块异常同样只降级自己。"""
    _seed_catalog()

    def _boom(code):
        raise ImportError('akshare broken')

    monkeypatch.setattr(ip, 'fetch_top_weights', _boom)
    monkeypatch.setattr(
        ip,
        'fetch_period_returns',
        lambda code: {'as_of': '2026-10-16', 'windows': {'1m': 1.0}, 'volatility_1y': None},
    )

    with closing(_market_db()) as db:
        profile = build_index_profile(db, '000300')

    assert profile['top_weights'] is None
    assert profile['period_returns'] is not None


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
    # #2278 新键必须存在（fixture 阻断外部 → None，但键缺失会让前端 undefined 而非「—」）
    assert 'publish_date' in data and 'cons_number' in data
    assert 'weighting_type' in data and 'currency' in data
    assert 'period_returns' in data and 'top_weights' in data


def test_endpoint_404_unknown(client, db):
    resp = client.get(PROFILE_URL, query_string={'symbol': '999999'})

    assert resp.status_code == 404
    assert resp.get_json()['error_code'] == 1002


def test_endpoint_422_missing_symbol(client, db):
    resp = client.get(PROFILE_URL)

    assert resp.status_code == 422
    assert resp.get_json()['error_code'] == 1001

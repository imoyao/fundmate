# -*- coding: utf-8 -*-
"""指数详情页关联 ETF 对比表（#2275 · P0）。

重点覆盖六件事：
1. **净值快照解析**：``fund_etf_fund_daily_em`` 动态日期列（两列取最新）、
   ``基金代码`` 主键 + 前导零防御、坏行丢弃、增长率坏值 → None；
2. **现货快照解析**：新浪 ``fund_etf_category_sina`` 代码 ``sh510300`` 形态抽数字
   归一为裸码、坏值 → None；
3. **行集来源**：``channel_links`` 只取 ``peer_role == 'etf'``（feeder 不进对比表）；
4. **跟踪差口径**：ETF 近 1 年 − 指数近 1 年（指数侧 monkeypatch），单边缺失 → None；
5. **降级矩阵**：快照两路全挂（名称仍在）/ 逐只日线全挂（returns 全 null）/
   无关联 ETF（rows=[] 不是错误）/ 名录未命中（None → 404）/
   规模/费率链各自独立降级（#2333，一链挂不拖累另一链）；
6. **TTL 缓存**：同码第二次构建零外部请求；聚合测试一律不联网（monkeypatch 全量）。
"""

from contextlib import closing
from datetime import date, timedelta

import pandas as pd
import pytest

from app.core.cache import CacheService
from app.core.db_factory import market_session_factory
from app.domains.indices.models import IndexCatalog
from app.services import etf_compare as ec
from app.services import index_metrics as im
from app.services.etf_compare import _pick_nav, _pick_spot, build_etf_compare

FIXED_TODAY = date(2026, 10, 17)


class _FixedDate(date):
    @classmethod
    def today(cls) -> date:
        return FIXED_TODAY


def _series(start: date, end: date, daily_growth: float = 1.001) -> list:
    days = (end - start).days + 1
    return [((start + timedelta(days=i)).isoformat(), round(1000.0 * daily_growth**i, 6)) for i in range(days)]


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """隔离：缓存注入 tmp_path、today 固定、外部源默认全空（具体用例再覆写）。"""
    monkeypatch.setattr(ec, '_ETF_COMPARE_CACHE', CacheService(namespace='test_etf_compare', file_dir=tmp_path))
    monkeypatch.setattr(ec, 'date', _FixedDate)
    monkeypatch.setattr(ec.direct_feeds, 'fetch_daily_tencent', lambda symbol, **k: [])
    # 指数侧收益默认给确定值（跟踪差基准）；具体用例可覆写
    monkeypatch.setattr(im, 'build_index_returns', lambda db, symbol: {'returns': {'y1': 10.0}})
    # 规模/费率（#2333）默认打空：聚合测试一律不联网，具体用例再覆写
    monkeypatch.setattr(ec, 'build_scale_map', lambda codes, nav_map: {})
    monkeypatch.setattr(ec, 'build_fee_map', lambda db, codes: {})
    yield


def _seed_catalog_row(code='931151', name='光伏产业', exchange='CSI'):
    with closing(market_session_factory()()) as db:
        row = db.query(IndexCatalog).filter(IndexCatalog.index_code == code).first()
        if row is None:
            row = IndexCatalog(index_code=code, name=name, source='csindex')
            db.add(row)
        row.name = name
        row.exchange = exchange
        db.commit()


def _patch_links(monkeypatch, links):
    """关联清单走 monkeypatch 而非种真实库：channel_links 是开发库实表，
    提交假行会污染数据且跨用例泄漏（实测踩坑）；关系查询逻辑由 related_symbols
    自己的测试负责，这里只验证「ETF 行集如何被消费」。"""

    def _fake(db, symbol):
        groups = []
        for item in links:
            if item['label'] not in groups:
                groups.append(item['label'])
        return {'links': list(links), 'groups': groups}

    monkeypatch.setattr(ec, 'build_related_symbols', _fake)


def _etf_link(code, name=None):
    return {
        'code': code,
        'name': name or f'名称{code}',
        'link_type': 'index_etf',
        'label': '同标的 ETF',
        'peer_role': 'etf',
    }


# ── 纯函数：快照解析 ──────────────────────────────────────────────────
def test_pick_nav_dynamic_date_columns():
    """两列动态日期净值取最新；前导零补齐；增长率坏值 → None；坏行丢弃。"""
    df = pd.DataFrame(
        [
            {'基金代码': '510300', '2026-10-16-单位净值': 4.01, '2026-10-15-单位净值': 4.0, '增长率': -0.25},
            {'基金代码': '159915', '2026-10-16-单位净值': 'bad', '2026-10-15-单位净值': 2.8, '增长率': 0.5},
            {'基金代码': '591', '2026-10-16-单位净值': 1.5, '2026-10-15-单位净值': 1.5, '增长率': 0.0},
        ]
    )
    out = _pick_nav(df)
    assert set(out) == {'510300', '000591'}  # 159915 净值坏行丢弃；'591' 补齐前导零
    assert out['510300'] == {'nav': 4.01, 'nav_date': '2026-10-16', 'nav_change_pct': -0.25}
    assert out['000591']['nav_date'] == '2026-10-16'


def test_pick_nav_empty_and_malformed():
    assert _pick_nav(pd.DataFrame()) == {}
    assert _pick_nav(pd.DataFrame([{'代码': '510300'}])) == {}  # 主键列名不是 基金代码 → 空防御


def test_pick_spot_sina_prefix_stripped():
    df = pd.DataFrame(
        [
            {'代码': 'sh510300', '最新价': 4.236, '涨跌幅': -0.141, '成交额': 16092791436},
            {'代码': 'sz159915', '最新价': 'x', '涨跌幅': None, '成交额': 'y'},
            {'代码': 'SH000001', '最新价': 1.0, '涨跌幅': 1.0, '成交额': 1.0},  # 非纯数字(指数) 仍抽数字
        ]
    )
    out = _pick_spot(df)
    assert out['510300'] == {'last': 4.236, 'change_pct': -0.141, 'amount': 16092791436}
    assert out['159915'] == {'last': None, 'change_pct': None, 'amount': None}  # 坏值 → None
    assert '000001' in out  # 前缀剥离不区分品种，行集由 channel_links 决定


# ── 编排层 ───────────────────────────────────────────────────────────
def test_unknown_index_returns_none():
    with closing(market_session_factory()()) as db:
        assert build_etf_compare(db, '999999') is None


def test_no_related_etfs_empty_rows(monkeypatch):
    """名录命中但无关联 ETF → 空形态（正常情形，不是错误）。"""
    _seed_catalog_row()
    _patch_links(monkeypatch, [])
    with closing(market_session_factory()()) as db:
        data = build_etf_compare(db, '931151')
    assert data == {'index_code': '931151', 'as_of': None, 'rows': []}


def _patch_akshare(monkeypatch, nav_df=None, spot_df=None, nav_exc=None, spot_exc=None):
    class _FakeAk:
        @staticmethod
        def fund_etf_fund_daily_em():
            if nav_exc is not None:
                raise nav_exc
            return nav_df

        @staticmethod
        def fund_etf_category_sina(symbol: str):
            if spot_exc is not None:
                raise spot_exc
            return spot_df

    monkeypatch.setattr('app.core.akshare_lazy.get_akshare', lambda: _FakeAk())


def test_compare_full_chain(monkeypatch):
    """全链路：只取 index_etf 的 ETF（feeder 不进表）、字段齐全、按成交额降序、跟踪差 = etf − index。"""
    _seed_catalog_row()
    _patch_links(
        monkeypatch,
        [
            _etf_link('510300'),
            _etf_link('159915'),
            {
                'code': '000051',
                'name': '联接基金',
                'link_type': 'etf_feeder',
                'label': '场外联接',
                'peer_role': 'feeder',
            },
        ],
    )
    nav_df = pd.DataFrame([{'基金代码': '510300', '2026-10-16-单位净值': 4.01, '增长率': -0.25}])
    spot_df = pd.DataFrame(
        [
            {'代码': 'sh510300', '最新价': 4.236, '涨跌幅': -0.141, '成交额': 100.0},
            {'代码': 'sz159915', '最新价': 2.789, '涨跌幅': -0.606, '成交额': 200.0},
        ]
    )
    _patch_akshare(monkeypatch, nav_df=nav_df, spot_df=spot_df)
    hist = _series(date(2025, 8, 1), date(2026, 10, 16))
    monkeypatch.setattr(ec.direct_feeds, 'fetch_daily_tencent', lambda symbol, **k: list(hist))

    with closing(market_session_factory()()) as db:
        data = build_etf_compare(db, '931151')

    assert [r['code'] for r in data['rows']] == ['159915', '510300']  # 成交额 200 > 100
    row300 = next(r for r in data['rows'] if r['code'] == '510300')
    assert row300['name'] == '名称510300'
    assert row300['nav'] == 4.01
    assert row300['nav_date'] == '2026-10-16'
    assert row300['change_pct'] == -0.141
    assert row300['amount'] == 100.0
    assert set(row300['returns']) == {'m1', 'm3', 'm6', 'y1'}  # ETF 窗口集（无 ytd/y2/y3）
    assert row300['returns']['y1'] is not None
    # 跟踪差 = ETF y1 − 指数 y1（指数侧 stub 给 10.0）
    assert row300['tracking_diff_y1'] == round(row300['returns']['y1'] - 10.0, 2)
    assert data['as_of'] == '2026-10-16'
    # index_returns 随包返回（对比表基准行数据源）；stub 仅给 y1
    assert 'index_returns' in data
    assert data['index_returns'] == {'y1': 10.0}


def test_compare_degrades_snapshot_and_hist(monkeypatch):
    """快照两路全挂 + 日线全挂：名称仍在、行情字段 None、returns 全 null、跟踪差 None。"""
    _seed_catalog_row()
    _patch_links(monkeypatch, [_etf_link('510300')])
    _patch_akshare(monkeypatch, nav_exc=RuntimeError('nav down'), spot_exc=RuntimeError('spot down'))

    with closing(market_session_factory()()) as db:
        data = build_etf_compare(db, '931151')

    assert len(data['rows']) == 1  # 表壳仍在（清单来自本地关系表）
    row = data['rows'][0]
    assert row['code'] == '510300' and row['name'] == '名称510300'
    assert row['nav'] is None and row['change_pct'] is None and row['amount'] is None
    assert row['returns'] == {'m1': None, 'm3': None, 'm6': None, 'y1': None}
    assert row['tracking_diff_y1'] is None
    assert row['scale_yi'] is None and row['mgmt_fee_pct'] is None and row['custody_fee_pct'] is None  # #2333
    assert data['as_of'] is None


def test_compare_tracking_diff_needs_both_sides(monkeypatch):
    """指数侧收益缺失 → 跟踪差 None（ETF 侧有值也不编数）。"""
    _seed_catalog_row()
    _patch_links(monkeypatch, [_etf_link('510300')])
    _patch_akshare(monkeypatch, nav_df=pd.DataFrame(), spot_df=pd.DataFrame())
    monkeypatch.setattr(im, 'build_index_returns', lambda db, symbol: None)
    monkeypatch.setattr(
        ec.direct_feeds, 'fetch_daily_tencent', lambda symbol, **k: _series(date(2025, 8, 1), date(2026, 10, 16))
    )

    with closing(market_session_factory()()) as db:
        data = build_etf_compare(db, '931151')

    assert data['rows'][0]['returns']['y1'] is not None
    assert data['rows'][0]['tracking_diff_y1'] is None


def test_as_of_common_trade_day_picks_min(monkeypatch):
    """as_of = 指数序列最新日 与 ETF 侧最新日的较小者（共同最新交易日）。"""
    _seed_catalog_row()
    _patch_links(monkeypatch, [_etf_link('510300')])
    nav_df = pd.DataFrame([{'基金代码': '510300', '2026-10-16-单位净值': 4.01, '增长率': -0.25}])
    spot_df = pd.DataFrame([{'代码': 'sh510300', '最新价': 4.236, '涨跌幅': -0.141, '成交额': 100.0}])
    _patch_akshare(monkeypatch, nav_df=nav_df, spot_df=spot_df)
    hist = _series(date(2025, 8, 1), date(2026, 10, 16))
    monkeypatch.setattr(ec.direct_feeds, 'fetch_daily_tencent', lambda symbol, **k: list(hist))
    # 指数侧序列最新日（2026-10-10）早于 ETF 净值日（2026-10-16）→ 取共同最新交易日 10-10
    monkeypatch.setattr(im, 'build_index_returns', lambda db, symbol: {'as_of': '2026-10-10', 'returns': {'y1': 10.0}})

    with closing(market_session_factory()()) as db:
        data = build_etf_compare(db, '931151')

    assert data['as_of'] == '2026-10-10'
    assert data['index_returns'] == {'y1': 10.0}


def test_compare_cached(monkeypatch):
    """整体 TTL 缓存：同码两次构建，akshare 与腾讯各只打一次。"""
    _seed_catalog_row()
    _patch_links(monkeypatch, [_etf_link('510300')])
    ak_calls, tx_calls = [], []

    class _FakeAk:
        @staticmethod
        def fund_etf_fund_daily_em():
            ak_calls.append('nav')
            return pd.DataFrame()

        @staticmethod
        def fund_etf_category_sina(symbol: str):
            ak_calls.append('spot')
            return pd.DataFrame()

    monkeypatch.setattr('app.core.akshare_lazy.get_akshare', lambda: _FakeAk())
    monkeypatch.setattr(
        ec.direct_feeds,
        'fetch_daily_tencent',
        lambda symbol, **k: (tx_calls.append(symbol), _series(date(2025, 8, 1), date(2026, 10, 16)))[1],
    )

    with closing(market_session_factory()()) as db:
        build_etf_compare(db, '931151')
        build_etf_compare(db, 'SH931151')

    assert ak_calls == ['nav', 'spot']
    assert tx_calls == ['510300']


def test_index_windows_parameterized():
    """compute_period_returns 窗口参数化（#2275 复用）：ETF 窗口集 + 关波动率。"""
    rows = _series(date(2025, 1, 1), date(2026, 10, 16))
    result = ec.compute_period_returns(rows, today=FIXED_TODAY, windows=ec._ETF_WINDOWS, volatility=False)
    assert set(result['returns']) == {'m1', 'm3', 'm6', 'y1'}
    assert result['volatility_y1'] is None  # 关闭后不计算，诚实 null


# ── 规模 / 费率接入（#2333）────────────────────────────────────────────
def test_compare_scale_fee_wired(monkeypatch):
    """规模/费率两链结果落行字段；codes 与 nav_map 正确传给规模链。"""
    _seed_catalog_row()
    _patch_links(monkeypatch, [_etf_link('510300')])
    _patch_akshare(
        monkeypatch,
        nav_df=pd.DataFrame([{'基金代码': '510300', '2026-10-16-单位净值': 4.01, '增长率': -0.25}]),
        spot_df=pd.DataFrame(),
    )
    seen = {}

    def _fake_scale(codes, nav_map):
        seen['codes'] = list(codes)
        seen['nav'] = (nav_map.get('510300') or {}).get('nav')
        return {'510300': 1209.5}

    def _fake_fee(db, codes):
        seen['fee_codes'] = list(codes)
        return {'510300': {'mgmt_fee_pct': 0.15, 'custody_fee_pct': 0.05}}

    monkeypatch.setattr(ec, 'build_scale_map', _fake_scale)
    monkeypatch.setattr(ec, 'build_fee_map', _fake_fee)

    with closing(market_session_factory()()) as db:
        data = build_etf_compare(db, '931151')

    row = data['rows'][0]
    assert row['scale_yi'] == 1209.5
    assert row['mgmt_fee_pct'] == 0.15
    assert row['custody_fee_pct'] == 0.05
    assert seen['codes'] == ['510300']
    assert seen['fee_codes'] == ['510300']
    assert seen['nav'] == 4.01  # 规模链拿到对比表净值链（沪市份额×净值口径需要）


def test_compare_scale_fee_independent_degrade(monkeypatch):
    """规模/费率各自独立降级：一链抛异常只让对应列 None，另一链照常落值。"""
    _seed_catalog_row()
    _patch_links(monkeypatch, [_etf_link('510300')])
    _patch_akshare(monkeypatch, nav_df=pd.DataFrame(), spot_df=pd.DataFrame())

    def _boom_scale(codes, nav_map):
        raise RuntimeError('exchange down')

    monkeypatch.setattr(ec, 'build_scale_map', _boom_scale)
    monkeypatch.setattr(
        ec, 'build_fee_map', lambda db, codes: {'510300': {'mgmt_fee_pct': 0.5, 'custody_fee_pct': 0.1}}
    )

    with closing(market_session_factory()()) as db:
        data = build_etf_compare(db, '931151')

    row = data['rows'][0]
    assert row['scale_yi'] is None  # 规模链挂 → 规模列 —
    assert row['mgmt_fee_pct'] == 0.5  # 费率链不受规模链拖累
    assert row['custody_fee_pct'] == 0.1


def test_compare_scale_fee_both_down_null(monkeypatch):
    """两链全挂：行字段 None（前端 —），整表不阻塞。"""
    _seed_catalog_row()
    _patch_links(monkeypatch, [_etf_link('510300')])
    _patch_akshare(monkeypatch, nav_df=pd.DataFrame(), spot_df=pd.DataFrame())
    monkeypatch.setattr(ec, 'build_scale_map', lambda codes, nav_map: (_ for _ in ()).throw(RuntimeError('all down')))
    monkeypatch.setattr(ec, 'build_fee_map', lambda db, codes: (_ for _ in ()).throw(RuntimeError('all down')))

    with closing(market_session_factory()()) as db:
        data = build_etf_compare(db, '931151')

    row = data['rows'][0]
    assert row['scale_yi'] is None
    assert row['mgmt_fee_pct'] is None
    assert row['custody_fee_pct'] is None
    assert row['code'] == '510300'  # 表壳仍在

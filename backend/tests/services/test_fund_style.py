# -*- coding: utf-8 -*-
"""基金投资风格箱（#2478）离线测试：adapter 解析 / job 去重与断点续传 / service / views。

硬口径（对应实施验收）：
  1. adapter：dates×styles 长度不一致必须抛错（错位矩阵静默截断比失败更糟）；
     ``cycle`` 必须为 ``'1y'``（``'all'`` 实测只返回近 37 点，勿被参数名误导）。
  2. job：``(fund_code, style_name, stat_date)`` 复合键去重 = 断点续传；
     dominant 派生「无源不写」；空目标池显式跳过（禁止退化全库逐只抓取）。
  3. service：固定展示序（上游调序不影响响应）；数据不足回 None 不用 0 顶替；
     组合加权走市值唯一口径，未覆盖持仓进 ``uncovered`` 不进加权、且进覆盖率分母。
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domains.funds.models import Fund, FundStyleExposure
from app.services.adapters.jiucaishuo_adapter import API_STYLE_HISTORY, JiucaishuoAdapter
from app.services.fund_style_service import (
    STYLE_DISPLAY_ORDER,
    get_fund_style_box,
    get_fund_style_history,
    portfolio_style_exposure,
)
from app.services.sync.jobs.fund_style_job import MAX_TARGETS, FundStyleSyncJob

# 上游 8 分类（测试夹具按展示序构造，断言顺序时更直观）
_EIGHT = list(STYLE_DISPLAY_ORDER)


def _style_resp(dates, rows):
    """构造上游响应。rows = [(风格名, [每时点值], color), ...]。"""
    return {
        'code': 0,
        'msg': '请求成功',
        'data': {
            'category_lists': dates,
            'info_lists': [{'name': n, 'data': vals, 'color': c} for n, vals, c in rows],
        },
    }


def _seed_box(db, fund_code, stat_date, box):
    """落一个时点的风格箱（box = {风格名: 值}）。"""
    for name, value in box.items():
        db.add(
            FundStyleExposure(
                fund_code=fund_code,
                stat_date=stat_date,
                style_name=name,
                value=Decimal(str(value)),
                source='jiucaishuo_style',
            )
        )
    db.commit()


# ── 1. adapter 解析 ──


def test_api_style_history_endpoint():
    assert API_STYLE_HISTORY.endswith('/v2/tubiao/get-style-history')


def test_parse_style_history_aligned():
    resp = _style_resp(
        ['2026-08-31', '2026-09-30'],
        [(n, [10.0 * (i + 1), 20.0 * (i + 1)], '#f50') for i, n in enumerate(_EIGHT)],
    )
    parsed = JiucaishuoAdapter.parse_style_history(resp)
    assert parsed['dates'] == ['2026-08-31', '2026-09-30']
    assert len(parsed['styles']) == 8
    assert parsed['styles'][0]['name'] == _EIGHT[0]
    assert parsed['styles'][0]['values'] == [10.0, 20.0]
    assert parsed['styles'][0]['color'] == '#f50'


def test_parse_style_history_length_mismatch_raises():
    """长度不一致 → 抛错。错位矩阵静默截断会让「大盘成长」顶上「固收风格」的值。"""
    resp = _style_resp(
        ['2026-08-31', '2026-09-30'],
        [('大盘成长', [10.0], '#f50')] + [(n, [5.0, 5.0], '') for n in _EIGHT[1:]],
    )
    with pytest.raises(ValueError, match='长度不一致'):
        JiucaishuoAdapter.parse_style_history(resp)


def test_parse_style_history_empty_raises():
    with pytest.raises(ValueError, match='无数据'):
        JiucaishuoAdapter.parse_style_history({'code': 0, 'data': {}})


def test_fetch_fund_style_history_uses_cycle_1y(monkeypatch):
    """cycle 必须 '1y'（'all' 只给近 37 点）。同时 fund_code 原样回带。"""
    captured = {}

    def fake_post(self, path, payload):
        captured['path'] = path
        captured['payload'] = payload
        return _style_resp(
            ['2026-09-30'],
            [(n, [12.5], '#f50') for n in _EIGHT],
        )

    monkeypatch.setattr(JiucaishuoAdapter, '_post', fake_post)
    parsed = JiucaishuoAdapter().fetch_fund_style_history('000001')
    assert captured['path'] == API_STYLE_HISTORY
    assert captured['payload']['cycle'] == '1y'
    assert captured['payload']['fund_code'] == '000001'
    assert parsed['fund_code'] == '000001'
    assert len(parsed['dates']) == 1


# ── 2. job：目标池 / 去重 / 断点续传 / 派生 ──


def test_resolve_pool_etf_normalize_and_stock_skip():
    job = FundStyleSyncJob(JiucaishuoAdapter(), None)
    pool = job.resolve_pool(['SZ159915', 'SH510300', 'SH600000', '000001'])
    # ETF 裸码归一化进池；带前缀的股票被剔除；裸 6 位码无法区分基金/股票，按基金进池
    # （上游对非基金返空 → _allow_empty_data 跳过，与 fund_position 同构）
    assert pool == ['159915', '510300', '000001']


def test_resolve_pool_empty_and_full_placeholder():
    job = FundStyleSyncJob(JiucaishuoAdapter(), None)
    assert job.resolve_pool([]) == []
    assert job.resolve_pool(['', '__full__', None]) == []


def test_resolve_pool_truncates_over_max():
    job = FundStyleSyncJob(JiucaishuoAdapter(), None)
    pool = job.resolve_pool([f'{i:06d}' for i in range(MAX_TARGETS + 3)])
    assert len(pool) == MAX_TARGETS


def test_run_empty_pool_skips_without_fetch():
    """空 targets = 显式跳过，不得退化为全库逐只抓取（data-strategy.md §4.3.3）。"""
    job = FundStyleSyncJob(JiucaishuoAdapter(), None)
    job._fetch_data = lambda *a, **k: pytest.fail('空池不应触发抓取')
    result = job.run(full_sync=False, targets=[])
    assert result['status'] == 'success'


def _mock_fetch(fund_code, dates, box_by_date):
    """按基金码返回风格箱全历史的假 fetch。"""

    def _fetch(self, code):
        if code != fund_code:
            return {'dates': [], 'styles': [], 'fund_code': code}
        styles = [{'name': n, 'color': '', 'values': [box_by_date[d][n] for d in dates]} for n in _EIGHT]
        return {'dates': list(dates), 'styles': styles, 'fund_code': code}

    return _fetch


def test_job_dedup_and_dominant_derivation(db, monkeypatch):
    """复合键去重 = 断点续传；dominant 派生只在有源时写。"""
    db.add(Fund(fund_code='000001', name='华夏成长'))
    db.commit()

    dates = ['2026-08-31', '2026-09-30', '2026-10-16']
    box_by_date = {
        '2026-08-31': dict(zip(_EIGHT, [40.0, 20.0, 10.0, 5.0, 10.0, 5.0, 0.0, 10.0])),
        '2026-09-30': dict(zip(_EIGHT, [45.0, 18.0, 10.0, 5.0, 8.0, 4.0, 0.0, 10.0])),
        '2026-10-16': dict(zip(_EIGHT, [50.0, 15.0, 10.0, 5.0, 6.0, 4.0, 0.0, 10.0])),
    }
    monkeypatch.setattr(JiucaishuoAdapter, 'fetch_fund_style_history', _mock_fetch('000001', dates, box_by_date))

    job = FundStyleSyncJob(JiucaishuoAdapter(), db)
    result = job.run(full_sync=False, targets=['000001'])
    assert result['status'] == 'success'

    # 首次跑 = 全量回补：3 时点 × 8 风格 = 24 行
    assert db.query(FundStyleExposure).count() == 24
    fund = db.query(Fund).filter_by(fund_code='000001').one()
    assert fund.dominant_style == '大盘成长'
    assert fund.style_period == '2026-10-16'

    # 第二次跑同样目标：去重后 0 新行（断点续传），标量不被无源覆盖
    job2 = FundStyleSyncJob(JiucaishuoAdapter(), db)
    job2.run(full_sync=False, targets=['000001'])
    assert db.query(FundStyleExposure).count() == 24
    fund = db.query(Fund).filter_by(fund_code='000001').one()
    assert fund.dominant_style == '大盘成长'
    assert fund.style_period == '2026-10-16'


def test_job_no_source_no_derivative(db, monkeypatch):
    """上游无数据（空 dates）→ 不插行、不写 dominant（无源即不派生）。"""
    db.add(Fund(fund_code='000002', name='某新基金', dominant_style=None, style_period=None))
    db.commit()
    monkeypatch.setattr(JiucaishuoAdapter, 'fetch_fund_style_history', _mock_fetch('000002', [], {}))

    job = FundStyleSyncJob(JiucaishuoAdapter(), db)
    result = job.run(full_sync=False, targets=['000002'])
    assert result['status'] == 'success'
    assert db.query(FundStyleExposure).count() == 0
    fund = db.query(Fund).filter_by(fund_code='000002').one()
    assert fund.dominant_style is None
    assert fund.style_period is None


# ── 3. service：读取 / 漂移 / 组合加权 ──


def test_style_box_order_dominant_and_drift(db):
    """固定展示序；dominant = 最新时点最大暴露；prev_dominant 给漂移信号。"""
    _seed_box(db, '000001', date(2026, 9, 30), dict(zip(_EIGHT, [40.0, 20.0, 10.0, 5.0, 10.0, 5.0, 0.0, 10.0])))
    _seed_box(db, '000001', date(2026, 10, 16), dict(zip(_EIGHT, [15.0, 50.0, 10.0, 5.0, 8.0, 4.0, 0.0, 8.0])))

    box = get_fund_style_box(db, '000001')
    assert box is not None
    assert [s['style_name'] for s in box['styles']] == _EIGHT
    assert box['stat_date'] == '2026-10-16'
    # 最新时点最大暴露 = 大盘价值 50（上期是 大盘成长 40 → 主导切换）
    assert box['dominant_style'] == '大盘价值'
    assert box['prev_dominant_style'] == '大盘成长'
    assert box['prev_period'] == '2026-09-30'
    assert box['dominant_changed'] is True


def test_style_box_none_for_missing(db):
    assert get_fund_style_box(db, '999999') is None
    assert get_fund_style_box(db, '') is None


def test_style_history_wide_and_limit(db):
    for i, d in enumerate([date(2026, 7, 31), date(2026, 8, 31), date(2026, 9, 30)]):
        _seed_box(db, '000001', d, dict(zip(_EIGHT, [10.0 * (i + 1)] + [12.5] * 7)))

    hist = get_fund_style_history(db, '000001')
    assert hist['count'] == 3
    assert [p['stat_date'] for p in hist['points']] == ['2026-09-30', '2026-08-31', '2026-07-31']  # 倒序
    assert hist['points'][0]['styles']['大盘成长'] == 30.0  # wide 形态

    limited = get_fund_style_history(db, '000001', limit=2)
    assert limited['count'] == 2
    assert [p['stat_date'] for p in limited['points']] == ['2026-09-30', '2026-08-31']

    # 非法/越界 limit 收敛到合法区间，不抛错（负值 → 1，超大 → 全量）
    assert get_fund_style_history(db, '000001', limit=-5)['count'] == 1
    assert get_fund_style_history(db, '000001', limit=10**6)['count'] == 3


def test_style_history_empty_for_missing(db):
    hist = get_fund_style_history(db, '999999')
    assert hist == {'fund_code': '999999', 'points': [], 'count': 0}


def test_portfolio_weighted_exposure(db):
    """加权数学 + 覆盖率诚实报告：未覆盖持仓进 uncovered、进分母、不进加权。"""
    # 基金 A：市值 1000 分，大盘成长 60 / 大盘价值 40
    # 基金 B：市值 3000 分，大盘成长 40 / 固收风格 60
    # 基金 C：无风格箱，市值 2000 分 → uncovered
    _seed_box(db, '000001', date(2026, 9, 30), {'大盘成长': 60.0, '大盘价值': 40.0})
    _seed_box(db, '000002', date(2026, 9, 30), {'大盘成长': 40.0, '固收风格': 60.0})

    from app.domains.positions.models import Position

    for code, mv in [('000001', 1000), ('000002', 3000), ('000003', 2000)]:
        db.add(
            Position(
                family_id=1,
                symbol=code,
                name=f'基金{code}',
                asset_type='fund',
                quantity=10000,
                market_value_override=mv,
            )
        )
    db.commit()

    result = portfolio_style_exposure(db, 1)
    by_name = {s['style_name']: s['value'] for s in result['styles']}
    # (1000×60 + 3000×40) / 4000 = 45.0；(1000×40)/4000 = 10.0；(3000×60)/4000 = 45.0
    assert by_name['大盘成长'] == 45.0
    assert by_name['大盘价值'] == 10.0
    assert by_name['固收风格'] == 45.0
    assert result['covered_market_value_cents'] == 4000
    assert result['total_market_value_cents'] == 6000
    assert result['coverage_pct'] == pytest.approx(66.67, abs=0.01)
    assert result['fund_count'] == 2
    assert result['period_from'] == result['period_to'] == '2026-09-30'
    # 每只箱体合计 = 100 → 加权合计恒 = 100
    assert sum(by_name.values()) == pytest.approx(100.0)
    uncovered = {u['symbol'] for u in result['uncovered']}
    assert uncovered == {'000003'}


def test_portfolio_weighted_exposure_etf_and_price_fallback(db):
    """ETF 带前缀 symbol 归一化；无净值无 override 时回退 current_price 快照价。"""
    _seed_box(db, '510300', date(2026, 9, 30), {'大盘成长': 45.6, '大盘价值': 18.0, '中盘成长': 36.4})

    from app.domains.positions.models import Position

    # 100 份 × 4.0 元 = 400 元 = 40000 分
    db.add(
        Position(
            family_id=1,
            symbol='SH510300',
            name='沪深300ETF',
            asset_type='etf',
            quantity=1000000,
            current_price=40000,
        )
    )
    db.commit()

    result = portfolio_style_exposure(db, 1)
    by_name = {s['style_name']: s['value'] for s in result['styles']}
    assert by_name['大盘成长'] == 45.6
    assert result['covered_market_value_cents'] == 40000
    assert result['coverage_pct'] == 100.0
    assert result['uncovered'] == []


def test_portfolio_no_positions_or_zero_value(db):
    assert portfolio_style_exposure(db, 1)['styles'] == []

    from app.domains.positions.models import Position

    db.add(Position(family_id=1, symbol='000001', name='零市值', asset_type='fund', quantity=0))
    db.commit()
    result = portfolio_style_exposure(db, 1)
    # 全 0 市值 → 权重无定义，诚实回空（不显示全零箱体）
    assert result['styles'] == []
    assert result['coverage_pct'] == 0.0
    assert [u['symbol'] for u in result['uncovered']] == ['000001']


# ── 4. views：三个只读端点 ──


def test_style_views(db, client):
    _seed_box(db, '000001', date(2026, 9, 30), dict(zip(_EIGHT, [40.0, 20.0, 10.0, 5.0, 10.0, 5.0, 0.0, 10.0])))
    _seed_box(db, '000001', date(2026, 10, 16), dict(zip(_EIGHT, [50.0, 15.0, 10.0, 5.0, 6.0, 4.0, 0.0, 10.0])))

    from app.domains.positions.models import Position

    db.add(
        Position(
            family_id=1,
            symbol='000001',
            name='华夏成长',
            asset_type='fund',
            quantity=10000,
            market_value_override=100000,
        )
    )
    db.commit()

    r = client.get('/api/funds/000001/style/latest/')
    assert r.status_code == 200
    body = r.get_json()
    assert body['data']['dominant_style'] == '大盘成长'
    assert body['data']['stat_date'] == '2026-10-16'
    assert len(body['data']['styles']) == 8

    r = client.get('/api/funds/000001/style/history/?limit=1')
    assert r.status_code == 200
    assert r.get_json()['data']['count'] == 1

    # 非法 limit 静默回退默认，不 400
    r = client.get('/api/funds/000001/style/history/?limit=abc')
    assert r.status_code == 200
    assert r.get_json()['data']['count'] == 2

    r = client.get('/api/funds/style/portfolio/')
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['coverage_pct'] == 100.0
    assert sum(s['value'] for s in data['styles']) == pytest.approx(100.0)

    # 无数据的基金 → data=null（前端降级「—」，不编造箱体）
    r = client.get('/api/funds/999999/style/latest/')
    assert r.status_code == 200
    assert r.get_json()['data'] is None

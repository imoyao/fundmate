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


# ── 2b. 可覆盖口径（#2628）：分母只含可能拿到箱体的持仓 ──


def _add_position(db, symbol, name, asset_type, mv, **kw):
    from app.domains.positions.models import Position

    db.add(
        Position(
            family_id=1,
            symbol=symbol,
            name=name,
            asset_type=asset_type,
            quantity=100,
            market_value_override=mv,
            **kw,
        )
    )


def test_portfolio_eligible_coverage_excludes_money_fund(db):
    """货基再大也不进可覆盖分母（#2628）：121 只持仓→8.35% 那个天花板就是这么来的。

    `coverage_pct` 保持 #2478 契约不变（全量持仓），两个口径并存、互不覆盖。
    """
    _seed_box(db, '000001', date(2026, 9, 30), {'大盘成长': 100.0})
    _add_position(db, '000001', '场外基金', 'fund', 1000)
    _add_position(db, '970164', '货币基金', 'money_fund', 9000)
    db.commit()

    result = portfolio_style_exposure(db, 1)

    assert result['total_market_value_cents'] == 10000
    # 旧口径：1000/10000 = 10%（含永远无箱体的货基）
    assert result['coverage_pct'] == pytest.approx(10.0)
    # 可覆盖口径：分母只剩那只场外基金
    assert result['eligible_market_value_cents'] == 1000
    assert result['eligible_coverage_pct'] == 100.0


def test_portfolio_eligible_coverage_null_when_no_eligible_asset(db):
    """没有任何可能带箱体的品种 → `None`，**不是 0%**（两种结论对用户意义不同）。"""
    _add_position(db, '970164', '货币基金', 'money_fund', 5000)
    db.commit()

    result = portfolio_style_exposure(db, 1)

    assert result['eligible_market_value_cents'] == 0
    assert result['eligible_coverage_pct'] is None
    assert result['coverage_pct'] == 0.0


def test_portfolio_eligible_coverage_excludes_qdii(db):
    """QDII 从可覆盖分母里摘掉：它的箱体口径存疑（韭圈儿实测把纳指100 判成固收风格），
    不该让它把「覆盖率」拉低，也不该让它拉高。"""
    _seed_box(db, '000001', date(2026, 9, 30), {'大盘成长': 100.0})
    db.add(Fund(fund_code='270042', name='广发纳斯达克100ETF联接(QDII)'))
    db.commit()
    _add_position(db, '000001', '场外基金', 'fund', 1000)
    _add_position(db, '270042', '纳指联接', 'fund', 3000)
    db.commit()

    result = portfolio_style_exposure(db, 1)

    assert result['has_qdii'] is True
    assert result['total_market_value_cents'] == 4000
    assert result['coverage_pct'] == pytest.approx(25.0)
    assert result['eligible_market_value_cents'] == 1000
    assert result['eligible_coverage_pct'] == 100.0


def test_portfolio_eligible_coverage_zero_when_eligible_but_uncovered(db):
    """有合格品种但一个都没箱体 → 0.0%（与「没有可覆盖资产」的 None 必须分得开）。"""
    _add_position(db, '000001', '无箱体基金', 'fund', 2000)
    db.commit()

    result = portfolio_style_exposure(db, 1)

    assert result['eligible_market_value_cents'] == 2000
    assert result['eligible_coverage_pct'] == 0.0


# ── 3b. 作用域（2026-10-27）：组合 / 账户 / 互斥 / 空作用域不回退 ──


def _make_portfolio(db, name='风格组合'):
    from app.domains.portfolios.models import Portfolio

    pf = Portfolio(family_id=1, name=name, is_deleted=False)
    db.add(pf)
    db.commit()
    return pf


def _attach_ledger(db, ledger_id, portfolio_id):
    from app.domains.ledgers.models import Ledger

    db.query(Ledger).filter(Ledger.id == ledger_id).update({'portfolio_id': portfolio_id})
    db.commit()


def test_portfolio_style_scope_portfolio(db, make_position):
    """组合口径 = 成员账本继承 + 持仓显式归属；组合外持仓不进结果。

    口径必须与 `services/scope.py` 一致（显式 `positions.portfolio_id` 优先，
    否则继承 `ledger.portfolio_id`）——手写「只按成员账本查」会漏掉显式归属那条路径，
    这正是穿透 / 归因把解析收敛成唯一出口的原因。
    """
    _seed_box(db, '000001', date(2026, 9, 30), {'大盘成长': 60.0, '大盘价值': 40.0})
    _seed_box(db, '000002', date(2026, 9, 30), {'大盘成长': 100.0})
    _seed_box(db, '000003', date(2026, 9, 30), {'固收风格': 100.0})

    pf = _make_portfolio(db)
    inherited = make_position(
        symbol='000001',
        name='继承',
        asset_type='fund',
        quantity=100,
        market_value_override=1000,
        account_name='组合账户甲',
    )
    _attach_ledger(db, inherited.ledger_id, pf.id)
    # 非成员账本，但持仓显式归属本组合 ⇒ 进结果
    make_position(
        symbol='000002',
        name='显式',
        asset_type='fund',
        quantity=100,
        market_value_override=3000,
        account_name='组合账户乙',
        portfolio_id=pf.id,
    )
    # 组合外：同一账本里的另一只基金 ⇒ 不进结果
    make_position(
        symbol='000003',
        name='组合外',
        asset_type='fund',
        quantity=100,
        market_value_override=2000,
        account_name='组合账户乙',
    )

    assert portfolio_style_exposure(db, 1)['total_market_value_cents'] == 6000

    scoped = portfolio_style_exposure(db, 1, portfolio_id=pf.id)
    by_name = {s['style_name']: s['value'] for s in scoped['styles']}
    # (1000×60) / 4000 = 15；(1000×40) / 4000 = 10；(3000×100) / 4000 = 75
    assert by_name['大盘成长'] == pytest.approx(90.0)
    assert by_name['大盘价值'] == pytest.approx(10.0)
    assert scoped['total_market_value_cents'] == 4000
    assert scoped['coverage_pct'] == 100.0


def test_portfolio_style_scope_ledger(db, make_position):
    """账户级只算该账本持仓（与组合级是两级不同粒度，不做隐式合并）。"""
    _seed_box(db, '000001', date(2026, 9, 30), {'大盘成长': 100.0})
    _seed_box(db, '000002', date(2026, 9, 30), {'固收风格': 100.0})

    pos_a = make_position(
        symbol='000001',
        name='甲',
        asset_type='fund',
        quantity=100,
        market_value_override=1000,
        account_name='风格账户甲',
    )
    make_position(
        symbol='000002',
        name='乙',
        asset_type='fund',
        quantity=100,
        market_value_override=3000,
        account_name='风格账户乙',
    )

    scoped = portfolio_style_exposure(db, 1, ledger_id=pos_a.ledger_id)
    assert scoped['total_market_value_cents'] == 1000
    assert [s['style_name'] for s in scoped['styles']] == ['大盘成长']


def test_portfolio_style_scope_empty_does_not_fall_back_to_family(db, make_position):
    """空作用域返回空结构，**不静默放大成家庭级**（#2595 同型错误的复活防线）。"""
    _seed_box(db, '000001', date(2026, 9, 30), {'大盘成长': 100.0})
    make_position(
        symbol='000001',
        name='甲',
        asset_type='fund',
        quantity=100,
        market_value_override=1000,
        account_name='风格账户甲',
    )
    empty_pf = _make_portfolio(db, '空组合')

    scoped = portfolio_style_exposure(db, 1, portfolio_id=empty_pf.id)
    assert scoped['styles'] == []
    assert scoped['total_market_value_cents'] == 0
    assert scoped['coverage_pct'] == 0.0
    assert scoped['uncovered'] == []
    # 家庭级照旧能看到这笔持仓（对比项：证明上面的空结果是作用域造成的，不是数据没了）
    assert portfolio_style_exposure(db, 1)['total_market_value_cents'] == 1000


def test_portfolio_style_scope_mutex_and_missing_portfolio(db):
    """互斥 / 组合不存在一律抛 ValueError（视图层转 400，与穿透 / 归因同款）。"""
    with pytest.raises(ValueError, match='互斥'):
        portfolio_style_exposure(db, 1, ledger_id=1, portfolio_id=1)
    with pytest.raises(ValueError, match='投资组合不存在'):
        portfolio_style_exposure(db, 1, portfolio_id=999999)


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


def test_style_portfolio_api_scope(db, client, make_position):
    """`?portfolio_id=` 走组合口径；互斥 / 组合不存在回 400 + error_code=1001。"""
    _seed_box(db, '000001', date(2026, 9, 30), {'大盘成长': 100.0})
    _seed_box(db, '000002', date(2026, 9, 30), {'固收风格': 100.0})

    pf = _make_portfolio(db, '接口组合')
    pos_a = make_position(
        symbol='000001',
        name='甲',
        asset_type='fund',
        quantity=100,
        market_value_override=1000,
        account_name='接口账户甲',
    )
    _attach_ledger(db, pos_a.ledger_id, pf.id)
    make_position(
        symbol='000002',
        name='乙',
        asset_type='fund',
        quantity=100,
        market_value_override=3000,
        account_name='接口账户乙',
    )

    r = client.get('/api/funds/style/portfolio/')
    assert r.status_code == 200
    assert r.get_json()['data']['total_market_value_cents'] == 4000

    r = client.get(f'/api/funds/style/portfolio/?portfolio_id={pf.id}')
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['total_market_value_cents'] == 1000
    assert [s['style_name'] for s in data['styles']] == ['大盘成长']

    r = client.get(f'/api/funds/style/portfolio/?ledger_id={pos_a.ledger_id}')
    assert r.status_code == 200
    assert r.get_json()['data']['total_market_value_cents'] == 1000

    r = client.get(f'/api/funds/style/portfolio/?ledger_id={pos_a.ledger_id}&portfolio_id={pf.id}')
    assert r.status_code == 400
    assert r.get_json()['error_code'] == 1001

    r = client.get('/api/funds/style/portfolio/?portfolio_id=999999')
    assert r.status_code == 400
    assert r.get_json()['error_code'] == 1001

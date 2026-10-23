# -*- coding: utf-8 -*-
"""#2134 账户/组合区间收益 vs 基准指数超额收益。

锁定五件事：
1. **指数区间涨跌幅**——首末可得收盘比 −1；不足 2 点 / 首末点超容差降级 None（不造 0）；
2. **基准选取**——CSI300 别名归一、未识别不顶替、非 CN_A 持仓降级、空默认沪深300；
3. **唯一口径**——账户级 range_rate 必须等于 `build_daily_pnl_series` 直接结果；
4. **组合级聚合**——Σ成员盈亏 ÷ Σ成员基线，**不是**成员收益率做平均（变异探针盯这条）；
5. **端点契约**——`{data, message, error_code}` 信封、必填/互斥参数 400。
"""

import datetime as dt

import pytest

from app.domains.funds.models import DailyWorth
from app.domains.indices.models import IndexDaily
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.services.analytics.benchmark_excess import (
    build_scope_excess,
    interval_benchmark_return,
    resolve_benchmark_code,
)
from app.services.pnl_calendar import build_daily_pnl_series

D1 = dt.date(2026, 1, 5)  # 买入日（基线前一日的资产从这天起有值）
D2 = dt.date(2026, 1, 6)  # 区间首日
D3 = dt.date(2026, 1, 7)  # 区间末日


def _add_nav(db, fund_code, date, unit_nav):
    db.add(DailyWorth(fund_code=fund_code, date=date, unit_nav=unit_nav))
    db.commit()


def _add_index(db, index_code, date, close):
    db.add(IndexDaily(index_code=index_code, trade_date=date, close=close, source='tencent'))
    db.commit()


def _seed_account(db, make_position, make_transaction, *, nav3=1.1):
    """账户 A：01-05 买入 1000 份 @1.0；01-07 净值 nav3（默认涨 10%）。"""
    pos = make_position(
        symbol='000031',
        name='基准超额测试基金',
        quantity=1000,
        avg_price=1.0,
        asset_type='fund',
        account_name='基准超额账户',
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=D1,
        symbol='000031',
    )
    db.commit()
    _add_nav(db, '000031', D1, 1.0)
    _add_nav(db, '000031', D2, 1.0)
    _add_nav(db, '000031', D3, nav3)
    return pos


# ── 1. 指数区间涨跌幅 ──────────────────────────────────────────────
def test_指数区间涨跌幅_首末收盘比(db):
    _add_index(db, '000300.SH', D2, 4000.0)
    _add_index(db, '000300.SH', D3, 4200.0)
    _add_index(db, '000300.SH', dt.date(2026, 1, 8), 4100.0)

    out = interval_benchmark_return(db, '000300.SH', D2, dt.date(2026, 1, 8))

    assert out['range_return'] == pytest.approx(2.5)
    assert out['bench_start_date'] == D2.isoformat()
    assert out['bench_end_date'] == dt.date(2026, 1, 8).isoformat()
    assert out['reason'] is None


def test_指数区间不足两点_降级不造0(db):
    _add_index(db, '000300.SH', D2, 4000.0)

    out = interval_benchmark_return(db, '000300.SH', D2, D3)

    assert out['range_return'] is None
    assert out['reason'] == 'index_insufficient_data'


def test_指数区间起点覆盖不足_降级(db):
    """首笔报价距区间起点 > 7 天（区间起点根本没有该指数数据）→ 降级。"""
    _add_index(db, '000688.SH', dt.date(2026, 1, 20), 1000.0)
    _add_index(db, '000688.SH', dt.date(2026, 1, 21), 1010.0)

    out = interval_benchmark_return(db, '000688.SH', D2, dt.date(2026, 1, 25))

    assert out['range_return'] is None
    assert out['reason'] == 'coverage_start_insufficient'


def test_指数区间终点覆盖不足_降级(db):
    _add_index(db, '000300.SH', D2, 4000.0)
    _add_index(db, '000300.SH', D3, 4200.0)

    out = interval_benchmark_return(db, '000300.SH', D2, dt.date(2026, 3, 1))

    assert out['range_return'] is None
    assert out['reason'] == 'coverage_end_insufficient'
    # 首/末点仍如实回填，供前端复核实际取数区间
    assert out['bench_start_date'] == D2.isoformat()
    assert out['bench_end_date'] == D3.isoformat()


# ── 2. 基准选取 ────────────────────────────────────────────────────
@pytest.mark.parametrize(
    'text,expected',
    [('CSI300', '000300.SH'), ('CSI500', '000905.SH'), ('沪深300', '000300.SH'), ('000905', '000905.SH')],
)
def test_基准文本归一到真相源(db, text, expected):
    code, reason = resolve_benchmark_code(db, family_id=1, benchmark_text=text)

    assert (code, reason) == (expected, None)


def test_基准文本未识别_不顶替不默认(db):
    code, reason = resolve_benchmark_code(db, family_id=1, benchmark_text='恒生指数')

    assert code is None
    assert reason == 'unrecognized_benchmark'


def test_基准未设置_默认沪深300(db):
    code, reason = resolve_benchmark_code(db, family_id=1, benchmark_text=None)

    assert (code, reason) == ('000300.SH', None)


def test_非CN_A持仓_降级不顶替(db, make_position):
    make_position(
        symbol='00700',
        name='港股持仓',
        quantity=100,
        avg_price=300.0,
        asset_type='stock',
        market='CN_HK',
        account_name='港美股账户',
    )
    db.commit()

    code, reason = resolve_benchmark_code(db, family_id=1, benchmark_text='CSI300')

    assert code is None
    assert reason == 'non_cn_a_holdings'


# ── 3. 账户级：唯一口径 ────────────────────────────────────────────
def test_账户级range_rate与引擎同源(db, make_position, make_transaction):
    pos = _seed_account(db, make_position, make_transaction)

    out = build_scope_excess(db, 1, '2026-01-06', '2026-01-07', ledger_id=pos.ledger_id)
    engine = build_daily_pnl_series(db, 1, '2026-01-06', '2026-01-07', ledger_id=pos.ledger_id)

    assert out['scope'] == 'ledger'
    assert out['range_rate'] == engine['range_rate'] == 10.0
    assert out['range_baseline'] == engine['range_baseline'] == 1000.0
    assert out['range_reason'] is None


def test_账户级excess等于账户收益率减指数涨幅(db, make_position, make_transaction):
    pos = _seed_account(db, make_position, make_transaction)
    _add_index(db, '000300.SH', D2, 4000.0)
    _add_index(db, '000300.SH', D3, 4200.0)

    out = build_scope_excess(db, 1, '2026-01-06', '2026-01-07', ledger_id=pos.ledger_id)

    assert out['benchmark']['code'] == '000300.SH'
    assert out['benchmark']['range_return'] == pytest.approx(5.0)
    assert out['excess_return'] == pytest.approx(5.0)  # 10.0 − 5.0


def test_指数缺失时excess诚实降级(db, make_position, make_transaction):
    pos = _seed_account(db, make_position, make_transaction)
    # 不造任何指数行 → 指数侧 None → excess None（不借 0）
    out = build_scope_excess(db, 1, '2026-01-06', '2026-01-07', ledger_id=pos.ledger_id)

    assert out['range_rate'] == 10.0
    assert out['benchmark']['range_return'] is None
    assert out['excess_return'] is None


# ── 4. 组合级：Σ分子 ÷ Σ分母（不是平均 rate）────────────────────
def _seed_portfolio(db, make_position, make_transaction):
    """组合两成员：A 涨 10%（分母 1000）、B 不动（分母 2000）。

    平均 rate = (10+0)/2 = 5%；正确聚合 = 100/3000 = 3.33%。两者可区分。
    """
    pf = Portfolio(name='基准超额组合', family_id=1, benchmark='CSI500')
    db.add(pf)
    db.flush()
    la = Ledger(name='组合成员A', ledger_type='fund', family_id=1, portfolio_id=pf.id)
    lb = Ledger(name='组合成员B', ledger_type='fund', family_id=1, portfolio_id=pf.id)
    db.add_all([la, lb])
    db.flush()

    pa = make_position(
        symbol='000031', name='成员A基金', quantity=1000, avg_price=1.0, asset_type='fund', ledger_id=la.id
    )
    pb = make_position(
        symbol='000046', name='成员B基金', quantity=2000, avg_price=1.0, asset_type='fund', ledger_id=lb.id
    )
    for pos, qty in ((pa, 1000), (pb, 2000)):
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            txn_type='buy',
            quantity=qty,
            price=1.0,
            confirm_date=D1,
            symbol=pos.symbol,
        )
    db.commit()
    _add_nav(db, '000031', D1, 1.0)
    _add_nav(db, '000031', D2, 1.0)
    _add_nav(db, '000031', D3, 1.1)
    _add_nav(db, '000046', D1, 1.0)
    _add_nav(db, '000046', D2, 1.0)
    _add_nav(db, '000046', D3, 1.0)
    return pf


def test_组合级聚合是分子和除以分母和(db, make_position, make_transaction):
    pf = _seed_portfolio(db, make_position, make_transaction)
    _add_index(db, '000905.SH', D2, 2000.0)
    _add_index(db, '000905.SH', D3, 2100.0)

    out = build_scope_excess(db, 1, '2026-01-06', '2026-01-07', portfolio_id=pf.id)

    assert out['scope'] == 'portfolio'
    assert out['range_pnl'] == pytest.approx(100.0)  # A 100 + B 0
    assert out['range_baseline'] == pytest.approx(3000.0)  # A 1000 + B 2000
    assert out['range_rate'] == pytest.approx(3.33)  # 100/3000，不是平均 (10+0)/2=5
    # CSI500 别名归一到 000905.SH（同一断言里锁基准选取）
    assert out['benchmark']['code'] == '000905.SH'
    assert out['benchmark']['range_return'] == pytest.approx(5.0)
    assert out['excess_return'] == pytest.approx(3.33 - 5.0)


def test_组合无成员_降级(db, make_position, make_transaction):
    pf = Portfolio(name='空组合', family_id=1)
    db.add(pf)
    db.commit()

    out = build_scope_excess(db, 1, '2026-01-06', '2026-01-07', portfolio_id=pf.id)

    assert out['range_rate'] is None
    assert out['range_reason'] == 'no_members'
    assert out['excess_return'] is None


def test_组合不存在_抛ValueError(db):
    with pytest.raises(ValueError):
        build_scope_excess(db, 1, '2026-01-06', '2026-01-07', portfolio_id=99999)


def test_参数互斥与区间倒挂(db):
    with pytest.raises(ValueError):
        build_scope_excess(db, 1, '2026-01-06', '2026-01-07', ledger_id=1, portfolio_id=2)
    with pytest.raises(ValueError):
        build_scope_excess(db, 1, '2026-01-09', '2026-01-06')
    with pytest.raises(ValueError):
        build_scope_excess(db, 1, 'not-a-date', '2026-01-06')


# ── 5. 端点契约 ────────────────────────────────────────────────────
def test_端点_200信封与关键字段(client, db, make_position, make_transaction):
    pos = _seed_account(db, make_position, make_transaction)
    _add_index(db, '000300.SH', D2, 4000.0)
    _add_index(db, '000300.SH', D3, 4200.0)

    resp = client.get(
        f'/api/summary/benchmark-excess/?start_date=2026-01-06&end_date=2026-01-07&ledger_id={pos.ledger_id}'
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['message'] == 'ok'
    data = payload['data']
    assert data['scope'] == 'ledger'
    assert data['range_rate'] == 10.0
    assert data['benchmark']['code'] == '000300.SH'
    assert data['excess_return'] == 5.0
    # None 必须以 null 出口（前端才能显示「—」而不是 0）
    assert b'"excess_return"' in resp.data


def test_端点_缺必填参数返回400(client):
    resp = client.get('/api/summary/benchmark-excess/')

    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload['error_code'] == 1001
    assert payload['data'] is None


def test_端点_ledger与portfolio同传返回400(client):
    resp = client.get(
        '/api/summary/benchmark-excess/?start_date=2026-01-06&end_date=2026-01-07&ledger_id=1&portfolio_id=2'
    )

    assert resp.status_code == 400
    assert resp.get_json()['error_code'] == 1001

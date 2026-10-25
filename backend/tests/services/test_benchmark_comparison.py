# -*- coding: utf-8 -*-
"""#2620 组合同期基准对比（超额 / 最大回撤 / 相关系数）。

锁定五件事：
1. **超额同期**——range_rate − 基准同区间涨跌幅，不年化、不换基准；
2. **回撤口径**——日收益连乘（TWR 链式），缺口日跳过不填 0；
3. **相关系数**——按对齐日收益、样本数一并返回；样本 < 3 或零波动回 None；
4. **基准缺失显式不可用**——`available=False` + `unavailable_reason` +
   `coverage_gaps` 给出缺口区间，**不插值、不兜底成 0**；
5. **显式基准覆盖**——传 `benchmark` 时只换基准侧，组合收益仍用同一份 range_rate。
"""

import datetime as dt

import pytest

from app.domains.funds.models import DailyWorth
from app.domains.indices.models import IndexDaily
from app.services.ai_recognizer.tools import ToolExecutor
from app.services.analytics.benchmark_comparison import build_benchmark_comparison

D1 = dt.date(2026, 1, 5)  # 买入日（区间基线）
D2 = dt.date(2026, 1, 6)  # 区间首日
D3 = dt.date(2026, 1, 7)
D4 = dt.date(2026, 1, 8)  # 区间末日


def _add_nav(db, fund_code, date, unit_nav):
    db.add(DailyWorth(fund_code=fund_code, date=date, unit_nav=unit_nav))
    db.commit()


def _add_index(db, index_code, date, close):
    db.add(IndexDaily(index_code=index_code, trade_date=date, close=close, source='tencent'))
    db.commit()


def _seed_position(db, make_position, make_transaction, *, navs, symbol='000031'):
    pos = make_position(
        symbol=symbol,
        name='基准对比测试基金',
        quantity=1000,
        avg_price=navs[0],
        asset_type='fund',
        account_name='基准对比账户',
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=navs[0],
        confirm_date=D1,
        symbol=symbol,
    )
    db.commit()
    for date, nav in zip([D1, D2, D3, D4], navs):
        _add_nav(db, symbol, date, nav)
    return pos


def test_正常路径_超额与回撤相关系数(db, make_position, make_transaction):
    """组合与基准日收益完全同步 ⇒ 相关系数 1、回撤相同、超额为两者之差。"""
    _seed_position(db, make_position, make_transaction, navs=[1.0, 0.95, 1.05, 1.10])
    for date, close in [(D1, 4000.0), (D2, 3800.0), (D3, 4200.0), (D4, 4400.0)]:
        _add_index(db, '000300.SH', date, close)

    d = build_benchmark_comparison(db, family_id=1, start_date=D2.isoformat(), end_date=D4.isoformat())

    assert d['available'] is True
    assert d['benchmark_code'] == '000300.SH'
    assert d['range_rate'] == pytest.approx(10.0, abs=0.01)
    assert d['benchmark_range_return'] == pytest.approx(15.79, abs=0.01)
    assert d['excess_return'] == pytest.approx(-5.79, abs=0.01)
    # 日收益完全同步 ⇒ 相关系数 1.0（3 个对齐样本）
    assert d['correlation_samples'] == 3
    assert d['correlation'] == pytest.approx(1.0, abs=1e-6)
    # 回撤按时序峰谷：1.0 → 0.95（−5%）→ 1.05 → 1.10，谷在峰值之后才回升 ⇒ 5%
    assert d['portfolio_max_drawdown_pct'] == pytest.approx(5.0, abs=0.02)
    assert d['benchmark_max_drawdown_pct'] == pytest.approx(5.0, abs=0.02)
    assert d['unavailable_reason'] is None


def test_基准不足两点_显式不可用并给缺口区间(db, make_position, make_transaction):
    """基准只有 1 个报价 ⇒ available False + 原因 + 整段缺口（不插值）。"""
    _seed_position(db, make_position, make_transaction, navs=[1.0, 0.95, 1.05, 1.10])
    _add_index(db, '000300.SH', D2, 3800.0)

    d = build_benchmark_comparison(db, family_id=1, start_date=D2.isoformat(), end_date=D4.isoformat())

    assert d['available'] is False
    assert d['unavailable_reason'] == 'index_insufficient_data'
    assert d['benchmark_range_return'] is None
    assert d['excess_return'] is None
    assert d['coverage_gaps'] == [{'from': D2.isoformat(), 'to': D4.isoformat()}]
    # 组合侧照常可算，不被基准缺失连坐
    assert d['range_rate'] == pytest.approx(10.0, abs=0.01)


def test_基准覆盖不全_缺口只报缺的那一段(db, make_position, make_transaction):
    """基准从 D3 才有报价（D2 缺）⇒ 缺口 = [D2, D2]，且 cover 起不够仍降级。"""
    _seed_position(db, make_position, make_transaction, navs=[1.0, 0.95, 1.05, 1.10])
    for date, close in [(D3, 4200.0), (D4, 4400.0)]:
        _add_index(db, '000300.SH', date, close)

    d = build_benchmark_comparison(db, family_id=1, start_date=D2.isoformat(), end_date=D4.isoformat())

    # 首点距区间起点 1 天 < 7 天容差 ⇒ 区间涨跌幅仍可算，但缺口如实报出
    assert d['available'] is True
    assert d['coverage_gaps'] == [{'from': D2.isoformat(), 'to': D2.isoformat()}]


def test_组合区间短于基准_正常可算(db, make_position, make_transaction):
    """只取 D3..D4：组合区间含 D3 当日涨跌（基线 = D2 末 950），基准前扩拿到前收盘。"""
    _seed_position(db, make_position, make_transaction, navs=[1.0, 0.95, 1.05, 1.10])
    for date, close in [(D1, 4000.0), (D2, 3800.0), (D3, 4200.0), (D4, 4400.0)]:
        _add_index(db, '000300.SH', date, close)

    d = build_benchmark_comparison(db, family_id=1, start_date=D3.isoformat(), end_date=D4.isoformat())

    assert d['available'] is True
    # 组合：(1100 − 950) / 950 ≈ 15.79%（收益日历口径含起点当日）
    assert d['range_rate'] == pytest.approx(15.79, abs=0.02)
    # 基准：(4200 → 4400) / 4200 ≈ 4.76%
    assert d['benchmark_range_return'] == pytest.approx(4.76, abs=0.02)


def test_零波动_相关系数为None而非0(db, make_position, make_transaction):
    """两侧都平盘 ⇒ 相关系数无定义（方差为 0），回 None 不造假 0。"""
    _seed_position(db, make_position, make_transaction, navs=[1.0, 1.0, 1.0, 1.0])
    for date in [D1, D2, D3, D4]:
        _add_index(db, '000300.SH', date, 4000.0)

    d = build_benchmark_comparison(db, family_id=1, start_date=D2.isoformat(), end_date=D4.isoformat())

    assert d['correlation'] is None
    assert d['correlation_samples'] == 3
    assert d['portfolio_max_drawdown_pct'] == pytest.approx(0.0, abs=0.01)
    assert d['excess_return'] == pytest.approx(0.0, abs=0.01)


def test_缺省全期起点为首笔确认日次日(db, make_position, make_transaction):
    """全期起点取次日：首笔交易当天前一天净资产为 0，当日起算必然 not_computable。

    变异探针：把起点改回确认日当日 ⇒ `range_rate` 变 None、`available` 变 False。
    """
    _seed_position(db, make_position, make_transaction, navs=[1.0, 0.95, 1.05, 1.10])
    for date, close in [(D1, 4000.0), (D2, 3800.0), (D3, 4200.0), (D4, 4400.0)]:
        _add_index(db, '000300.SH', date, close)

    d = build_benchmark_comparison(db, family_id=1, end_date=D4.isoformat())

    assert d['start_date'] == D2.isoformat()
    assert d['available'] is True
    assert d['range_rate'] is not None


def test_区间起点无资产_降级no_baseline(db, make_position, make_transaction):
    """区间起点时账户还没建仓 ⇒ 分母为 0，reason 细化为 no_baseline（不是笼统 not_computable）。"""
    pos = make_position(
        symbol='000032',
        name='晚建仓基金',
        quantity=1000,
        avg_price=1.0,
        asset_type='fund',
        account_name='晚建仓账户',
        confirm_date=D3,
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=D3,
        symbol='000032',
    )
    db.commit()
    for date, nav in [(D3, 1.0), (D4, 1.1)]:
        _add_nav(db, '000032', date, nav)
    for date, close in [(D1, 4000.0), (D2, 3800.0), (D3, 4200.0), (D4, 4400.0)]:
        _add_index(db, '000300.SH', date, close)

    d = build_benchmark_comparison(db, family_id=1, start_date=D1.isoformat(), end_date=D4.isoformat())

    assert d['available'] is False
    assert d['unavailable_reason'] == 'no_baseline'
    assert d['range_rate'] is None


def test_显式基准覆盖_只换基准侧(db, make_position, make_transaction):
    """显式传中证500：组合收益不变，基准与超额按中证500重算。"""
    _seed_position(db, make_position, make_transaction, navs=[1.0, 0.95, 1.05, 1.10])
    for date, close in [(D1, 4000.0), (D2, 3800.0), (D3, 4200.0), (D4, 4400.0)]:
        _add_index(db, '000300.SH', date, close)
    for date, close in [(D1, 6000.0), (D2, 6000.0), (D3, 6300.0), (D4, 6600.0)]:
        _add_index(db, '000905.SH', date, close)

    d = build_benchmark_comparison(
        db, family_id=1, start_date=D2.isoformat(), end_date=D4.isoformat(), benchmark_code='000905.SH'
    )

    assert d['benchmark_code'] == '000905.SH'
    assert d['range_rate'] == pytest.approx(10.0, abs=0.01)
    assert d['benchmark_range_return'] == pytest.approx(10.0, abs=0.01)
    assert d['excess_return'] == pytest.approx(0.0, abs=0.02)


def test_基准不在白名单抛ValueError(db):
    with pytest.raises(ValueError, match='benchmark 仅支持'):
        build_benchmark_comparison(
            db, family_id=1, start_date=D2.isoformat(), end_date=D4.isoformat(), benchmark_code='HSI'
        )


# ── 工具层：schema 校验与真实调用 ──────────────────────────────────
def test_工具层_正常调用(db, make_position, make_transaction):
    _seed_position(db, make_position, make_transaction, navs=[1.0, 0.95, 1.05, 1.10])
    for date, close in [(D1, 4000.0), (D2, 3800.0), (D3, 4200.0), (D4, 4400.0)]:
        _add_index(db, '000300.SH', date, close)

    r = ToolExecutor.run(
        'get_portfolio_vs_benchmark',
        {'start_date': D2.isoformat(), 'end_date': D4.isoformat()},
    )
    assert r['status'] == 'success', r.get('msg')
    assert r['data']['available'] is True
    assert r['data']['excess_return'] == pytest.approx(-5.79, abs=0.02)


def test_工具层_基准不在允许值被拒绝():
    r = ToolExecutor.run('get_portfolio_vs_benchmark', {'benchmark': 'HSI'})
    assert r['status'] == 'error'
    assert '不在允许值' in r['msg']


def test_工具层_日期格式非法被拒绝():
    r = ToolExecutor.run('get_portfolio_vs_benchmark', {'start_date': '2026/01/06'})
    assert r['status'] == 'error'
    assert '不匹配格式' in r['msg']

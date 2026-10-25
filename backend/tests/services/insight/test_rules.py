# -*- coding: utf-8 -*-
"""规则驱动静态诊断的单测（#1017 / #2603）。

只测**规则层**（纯函数，喂快照）：规则的判据是阈值与边界，不是数据库往返。
取数层（engine）另有接口契约测试兜底。

钉住四件事：
1. 阈值边界（恰好等于阈值算触发、差一点不算）；
2. 行业规则在穿透率过低时**不触发**（占比不可信，宁可不提示）；
3. 缺数据（无持仓 / 无最近交易日）不产生提示，也不抛异常；
4. `evidence` 带原始数值（能复核「凭什么是这条」），`message` 面向用户。

#2603 追加：风格规则（`style_concentration`）的同类钉死 —— 覆盖率门槛、
QDII 口径标注、以及「规则只读快照、不查库」这条结构约束。
"""

import inspect

import pytest

from app.services.insight.rules import (
    INDUSTRY_LIMIT,
    INDUSTRY_MIN_COVERAGE,
    MIN_HOLDINGS,
    RULES,
    SINGLE_NAME_LIMIT,
    STYLE_LIMIT_PCT,
    STYLE_MIN_COVERAGE_PCT,
    evaluate,
)


def _snapshot(**overrides):
    # 5 只各 20%：稳定不触发集中度与分散度，便于逐条隔离被测规则
    base = {
        'holdings': [{'symbol': f'00000{i}', 'name': f'基金{i}', 'market_value_cents': 200_000} for i in range(1, 6)],
        'total_cents': 1_000_000,
        'holding_count': 5,
        'top_industry': None,
        'penetration_ratio': 0.0,
        'latest_day': None,
        'style_exposure': None,
    }
    base.update(overrides)
    return base


def _style_exposure(**overrides):
    """一份「风格明显偏斜且覆盖率达标」的快照片段。"""
    base = {
        'styles': [
            {'style_name': '大盘成长', 'value': 62.5},
            {'style_name': '中盘价值', 'value': 20.0},
            {'style_name': '固收风格', 'value': 17.5},
        ],
        'coverage_pct': 88.6,
        'fund_count': 4,
        'period_from': '2026-09-30',
        'period_to': '2026-09-30',
        'has_qdii': False,
    }
    base.update(overrides)
    return base


def _codes(tips):
    return [tip['code'] for tip in tips]


def test_规则注册表不为空且code唯一():
    assert RULES
    codes = [rule.code for rule in RULES]
    assert len(codes) == len(set(codes))


def test_均衡持仓不触发任何提示():
    assert evaluate(_snapshot()) == []


def test_单一标的恰好到阈值即触发():
    # 25% 恰好等于上限 → 触发（判据是「≥」）
    snapshot = _snapshot(
        holdings=[{'symbol': '000001', 'name': '甲基金', 'market_value_cents': 250_000}],
        total_cents=1_000_000,
        holding_count=1,
    )
    tips = evaluate(snapshot)
    assert 'single_name_concentration' in _codes(tips)
    tip = next(t for t in tips if t['code'] == 'single_name_concentration')
    assert tip['evidence']['ratio'] == pytest.approx(SINGLE_NAME_LIMIT)
    assert '甲基金' in tip['message']


def test_单一标的略低于阈值不触发():
    snapshot = _snapshot(
        holdings=[{'symbol': '000001', 'name': '甲基金', 'market_value_cents': 249_000}],
        total_cents=1_000_000,
        holding_count=3,
    )
    assert 'single_name_concentration' not in _codes(evaluate(snapshot))


def test_行业集中但穿透率过低不触发():
    industry = {'name': '制造业', 'ratio_of_penetrated': 0.75}
    # 穿透率 10% < 30% 门槛：占比不可信
    assert 'industry_concentration' not in _codes(
        evaluate(_snapshot(top_industry=industry, penetration_ratio=INDUSTRY_MIN_COVERAGE - 0.01))
    )
    # 穿透率达标 + 行业占比达上限 → 触发
    tips = evaluate(_snapshot(top_industry=industry, penetration_ratio=0.55))
    assert 'industry_concentration' in _codes(tips)
    assert tips[0]['evidence']['penetration_ratio'] == pytest.approx(0.55)


def test_行业占比低于阈值不触发():
    industry = {'name': '制造业', 'ratio_of_penetrated': INDUSTRY_LIMIT - 0.01}
    assert 'industry_concentration' not in _codes(evaluate(_snapshot(top_industry=industry, penetration_ratio=0.9)))


def test_持仓数少于下限触发分散不足():
    snapshot = _snapshot(
        holdings=[{'symbol': '000001', 'name': '甲基金', 'market_value_cents': 100_000}],
        total_cents=100_000,
        holding_count=MIN_HOLDINGS - 1,
    )
    tips = evaluate(snapshot)
    assert 'low_diversification' in _codes(tips)


def test_空账户不产生提示():
    empty = _snapshot(holdings=[], total_cents=0, holding_count=0)
    assert evaluate(empty) == []


def test_单日跌幅触发与不触发():
    assert 'portfolio_day_drop' not in _codes(evaluate(_snapshot(latest_day={'date': '2026-10-23', 'rate_pct': -1.5})))
    tips = evaluate(_snapshot(latest_day={'date': '2026-10-23', 'rate_pct': -2.0}))
    assert 'portfolio_day_drop' in _codes(tips)
    assert tips[0]['evidence']['date'] == '2026-10-23'


def test_缺最近交易日不触发也不抛异常():
    assert evaluate(_snapshot(latest_day=None)) == []


def test_接口契约(client):
    resp = client.get('/api/insight/tips/')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['message'] == 'ok'
    data = payload['data']
    assert isinstance(data['items'], list)
    assert data['count'] == len(data['items'])
    assert set(data['snapshot']) == {
        'holding_count',
        'total_value_cents',
        'penetration_ratio',
        'latest_day',
        'style_coverage_pct',
    }


# ── #2603 风格规则 ────────────────────────────────────────────────


def test_风格暴露超阈值触发提示():
    tips = evaluate(_snapshot(style_exposure=_style_exposure()))
    assert 'style_concentration' in _codes(tips)
    tip = next(t for t in tips if t['code'] == 'style_concentration')
    assert tip['evidence']['style_name'] == '大盘成长'
    assert tip['evidence']['value_pct'] == pytest.approx(62.5)
    assert tip['evidence']['limit_pct'] == STYLE_LIMIT_PCT
    assert '大盘成长' in tip['message']


def test_风格暴露恰好到阈值即触发():
    # 阈值判据是「≥」：恰好 40.0 也要触发
    style = _style_exposure(styles=[{'style_name': '大盘成长', 'value': STYLE_LIMIT_PCT}])
    tips = evaluate(_snapshot(style_exposure=style))
    assert 'style_concentration' in _codes(tips)


def test_风格暴露略低于阈值不触发():
    style = _style_exposure(styles=[{'style_name': '大盘成长', 'value': STYLE_LIMIT_PCT - 0.01}])
    assert 'style_concentration' not in _codes(evaluate(_snapshot(style_exposure=style)))


def test_风格覆盖率不足不触发():
    # 覆盖率 30% < 50% 门槛：样本太少，「某风格占 62%」可能是假象
    style = _style_exposure(coverage_pct=STYLE_MIN_COVERAGE_PCT - 0.01)
    assert 'style_concentration' not in _codes(evaluate(_snapshot(style_exposure=style)))


def test_风格取数失败时其余规则仍触发():
    # 风格维度整体缺失（取数失败/无风格箱数据）→ 风格规则不触发，但**别的规则照跑**
    tips = evaluate(_snapshot(style_exposure=None, latest_day={'date': '2026-10-23', 'rate_pct': -3.0}))
    assert 'style_concentration' not in _codes(tips)
    assert 'portfolio_day_drop' in _codes(tips)


def test_风格提示标注QDII口径存疑():
    style = _style_exposure(has_qdii=True)
    tips = evaluate(_snapshot(style_exposure=style))
    tip = next(t for t in tips if t['code'] == 'style_concentration')
    assert tip['evidence']['has_qdii'] is True
    assert 'QDII' in tip['message']


def test_风格提示不含QDII时不加口径说明():
    tip = next(t for t in evaluate(_snapshot(style_exposure=_style_exposure())) if t['code'] == 'style_concentration')
    assert 'QDII' not in tip['message']


def test_风格规则只读快照():
    # 结构约束：规则的 check 只收一个快照参数，不给 db 入口
    # （否则「一条规则一次查询」的 N+1 会回来，且单测必须碰数据库）
    rule = next(r for r in RULES if r.code == 'style_concentration')
    params = inspect.signature(rule.check).parameters
    assert len(params) == 1
    assert 'db' not in params
    assert 'session' not in params

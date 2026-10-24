# -*- coding: utf-8 -*-
"""规则驱动静态诊断的单测（#1017）。

只测**规则层**（纯函数，喂快照）：规则的判据是阈值与边界，不是数据库往返。
取数层（engine）另有接口契约测试兜底。

钉住四件事：
1. 阈值边界（恰好等于阈值算触发、差一点不算）；
2. 行业规则在穿透率过低时**不触发**（占比不可信，宁可不提示）；
3. 缺数据（无持仓 / 无最近交易日）不产生提示，也不抛异常；
4. `evidence` 带原始数值（能复核「凭什么是这条」），`message` 面向用户。
"""

import pytest

from app.services.insight.rules import (
    INDUSTRY_LIMIT,
    INDUSTRY_MIN_COVERAGE,
    MIN_HOLDINGS,
    RULES,
    SINGLE_NAME_LIMIT,
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
    }

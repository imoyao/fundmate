# -*- coding: utf-8 -*-
"""Q3 再平衡客观参考信号的纯计算单测（#3049 §10 / #3050 验收锚点）。

这组用例同时是防幻觉回归网：算不出的数据必须进 ``missing_signals``，
不得补 0、不得近似、不得出现方向性买卖措辞。
"""

import json

import pytest

from app.services.analytics.rebalance_reference_rules import (
    CAUTION_WEIGHT_PCT,
    DISCLAIMER,
    UNAVAILABLE_SIGNALS,
    VALID_LEVELS,
    WATCH_WEIGHT_PCT,
    build_rebalance_report,
    valuation_label,
    weight_level,
)

AS_OF = '2026-11-11'
SCOPE = 'family_id=1'


def _report(positions, valuation=None):
    return build_rebalance_report(positions=positions, as_of=AS_OF, scope=SCOPE, valuation=valuation)


def _signals_of(report, kind):
    return [s for s in report['signals'] if s['type'] == kind]


def test_empty_positions_declare_gap_and_never_fabricate_zero():
    report = _report([])
    assert _signals_of(report, 'single_position_weight') == []
    assert report['coverage']['total_market_value_yuan'] == 0
    assert any(m['type'] == 'single_position_weight' and '不补 0' in m['reason'] for m in report['missing_signals'])


def test_invalid_market_values_are_excluded_not_counted_as_zero():
    report = _report(
        [
            {'symbol': 'A', 'name': '甲', 'market_value': 60.0},
            {'symbol': 'B', 'name': '乙', 'market_value': None},
            {'symbol': 'C', 'name': '丙', 'market_value': 0},
            {'symbol': 'D', 'name': '丁', 'market_value': 'bad'},
        ]
    )
    assert report['coverage']['position_count'] == 1
    assert report['coverage']['excluded_count'] == 3
    assert _signals_of(report, 'single_position_weight')[0]['weight_pct'] == 100.0


def test_weight_uses_total_market_value_as_denominator():
    report = _report(
        [
            {'symbol': '161725', 'name': '招商中证白酒', 'market_value': 38.2},
            {'symbol': '110011', 'name': '易方达中小盘', 'market_value': 61.8},
        ]
    )
    weights = _signals_of(report, 'single_position_weight')
    assert [w['symbol'] for w in weights] == ['110011', '161725']
    assert weights[0]['weight_pct'] == 61.8
    assert weights[1]['weight_pct'] == 38.2


@pytest.mark.parametrize(
    'pct,expected',
    [
        (WATCH_WEIGHT_PCT - 0.01, 'info'),
        (WATCH_WEIGHT_PCT, 'watch'),
        (CAUTION_WEIGHT_PCT - 0.01, 'watch'),
        (CAUTION_WEIGHT_PCT, 'caution'),
        (90.0, 'caution'),
    ],
)
def test_weight_level_boundaries(pct, expected):
    assert weight_level(pct) == expected


def test_top1_is_still_reported_when_nothing_exceeds_watch():
    report = _report([{'symbol': str(i), 'name': f'标的{i}', 'market_value': 10.0} for i in range(6)])
    weights = _signals_of(report, 'single_position_weight')
    assert len(weights) == 1
    assert weights[0]['level'] == 'info'
    assert weights[0]['weight_pct'] == 16.67


@pytest.mark.parametrize(
    'percentile,label,level',
    [(90.0, '估值偏高', 'watch'), (80.0, '估值正常', 'info'), (71.0, '估值正常', 'info'), (10.0, '估值偏低', 'watch')],
)
def test_valuation_bands(percentile, label, level):
    assert valuation_label(percentile) == label
    report = _report(
        [{'symbol': 'A', 'name': '甲', 'market_value': 100.0}],
        valuation={'index': '000300.SH', 'pe_percentile': percentile, 'valuation_date': '2026-11-10'},
    )
    signal = _signals_of(report, 'valuation_context')[0]
    assert signal['note'] == label
    assert signal['level'] == level
    assert signal['pe_percentile'] == percentile


def test_missing_valuation_is_declared_not_defaulted_to_zero():
    report = _report([{'symbol': 'A', 'name': '甲', 'market_value': 100.0}], valuation=None)
    assert _signals_of(report, 'valuation_context') == []
    assert any(m['type'] == 'valuation_context' and '无' in m['reason'] for m in report['missing_signals'])


def test_unavailable_signals_are_always_declared():
    report = _report([{'symbol': 'A', 'name': '甲', 'market_value': 100.0}])
    declared = {m['type'] for m in report['missing_signals']}
    assert {name for name, _ in UNAVAILABLE_SIGNALS} <= declared
    assert not _signals_of(report, 'industry_concentration')
    assert not _signals_of(report, 'deviation_from_mean')


def test_output_has_disclaimer_and_only_three_levels():
    report = _report(
        [{'symbol': 'A', 'name': '甲', 'market_value': 100.0}],
        valuation={'index': '000300.SH', 'pe_percentile': 95},
    )
    assert report['disclaimer'] == DISCLAIMER
    assert report['as_of'] == AS_OF and report['scope'] == SCOPE
    assert {s['level'] for s in report['signals']} <= VALID_LEVELS


def test_no_directional_advice_in_output():
    """防幻觉硬约束：输出里不能出现模型可自由发挥的买卖方向词。"""
    report = _report(
        [{'symbol': 'A', 'name': '甲', 'market_value': 100.0}],
        valuation={'index': '000300.SH', 'pe_percentile': 95},
    )
    payload = json.dumps(report, ensure_ascii=False)
    for word in ('买入', '卖出', '加仓', '减仓', '推荐', '应该买', '应该卖'):
        assert word not in payload, f'输出出现方向性措辞：{word}'

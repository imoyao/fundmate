# -*- coding: utf-8 -*-
"""Q3 再平衡客观参考信号的纯计算单测（#3049 §10 / D112 验收锚点）。

这组用例同时是防幻觉回归网：算不出的数据必须进 ``missing_signals``，
不得补 0、不得近似、不得出现方向性买卖措辞。v2 起两类信号不再是恒定缺口：
有事实必须真算出来，没事实必须逐条声明原因。
"""

import json

import pytest

from app.services.analytics.rebalance_reference_rules import (
    CAUTION_WEIGHT_PCT,
    DISCLAIMER,
    INDUSTRY_CAUTION_SHARE_PCT,
    UNAVAILABLE_SIGNALS,
    VALID_LEVELS,
    WATCH_WEIGHT_PCT,
    build_rebalance_report,
    valuation_label,
    weight_level,
)

AS_OF = '2026-11-11'
SCOPE = 'family_id=1'

POSITIONS = [
    {'symbol': '110011', 'name': '甲基金', 'market_value': 55.0},
    {'symbol': '600000', 'name': '乙股票', 'market_value': 45.0},
]
INDUSTRY_FACT = {
    'scheme': 'csrc',
    'scheme_label': '证监会门类',
    'penetrated_ratio': 0.5312,
    'industries': [
        {'code': 'C', 'name': '制造业', 'value_cny': 60.0, 'ratio_of_penetrated': 0.6},
        {'code': 'J', 'name': '金融业', 'value_cny': 40.0, 'ratio_of_penetrated': 0.4},
    ],
}
HISTORY_FACT = {
    'window_days': 90,
    'sample_days': 13,
    'means': {'110011': 42.0, '600000': 58.0},
    'as_of': '2026-11-12',
}
FUND_FACT = {'items': [{'symbol': '110011', 'pe_percentile': 88, 'valuation_date': '2026-11-11'}]}


def _report(positions, valuation=None, **facts):
    return build_rebalance_report(positions=positions, as_of=AS_OF, scope=SCOPE, valuation=valuation, **facts)


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


def test_v2_gaps_are_declared_until_facts_arrive():
    """没数据时三类 v2 信号都要显式声明原因，且绝不出现在 signals 里。"""
    report = _report([{'symbol': 'A', 'name': '甲', 'market_value': 100.0}])
    declared = {m['type'] for m in report['missing_signals']}
    assert {name for name, _ in UNAVAILABLE_SIGNALS} <= declared
    assert {'industry_concentration', 'deviation_from_mean'} <= declared
    assert not _signals_of(report, 'industry_concentration')
    assert not _signals_of(report, 'deviation_from_mean')
    assert not _signals_of(report, 'fund_valuation_percentile')
    assert all(m['reason'] for m in report['missing_signals'])


def test_v2_signals_replace_gaps_when_facts_arrive():
    """事实齐备时，三类信号必须真出数，且从 missing_signals 中撤下。"""
    report = _report(POSITIONS, industry=INDUSTRY_FACT, history=HISTORY_FACT, fund_valuation=FUND_FACT)
    declared = {m['type'] for m in report['missing_signals']}
    assert not {'industry_concentration', 'deviation_from_mean', 'fund_valuation_percentile'} & declared
    assert len(_signals_of(report, 'industry_concentration')) == 1
    assert len(_signals_of(report, 'deviation_from_mean')) == 2
    assert len(_signals_of(report, 'fund_valuation_percentile')) == 1
    assert {s['level'] for s in report['signals']} <= VALID_LEVELS


def test_industry_signal_uses_csrc_and_discloses_coverage():
    signal = _signals_of(_report(POSITIONS, industry=INDUSTRY_FACT), 'industry_concentration')[0]
    assert signal['scheme'] == 'csrc'
    assert signal['top_industry'] == '制造业'
    assert signal['share_pct'] == 60.0
    assert signal['hhi'] == 0.52
    assert signal['coverage_pct'] == 53.12
    assert signal['level'] == 'caution'
    assert signal['share_pct'] >= INDUSTRY_CAUTION_SHARE_PCT


def test_industry_signal_never_normalizes_unpenetrated_part():
    """覆盖率只有 20% 时，行业占比仍只按已穿透部分算，不假装覆盖整个组合。"""
    signal = _signals_of(
        _report(POSITIONS, industry=dict(INDUSTRY_FACT, penetrated_ratio=0.2)),
        'industry_concentration',
    )[0]
    assert signal['share_pct'] == 60.0
    assert signal['coverage_pct'] == 20.0


def test_industry_signal_without_values_is_a_gap():
    fact = dict(INDUSTRY_FACT, industries=[{'code': 'C', 'name': '制造业', 'value_cny': 0}])
    report = _report(POSITIONS, industry=fact)
    assert not _signals_of(report, 'industry_concentration')
    assert any(m['type'] == 'industry_concentration' for m in report['missing_signals'])


def test_deviation_signals_are_current_minus_mean():
    signals = _signals_of(_report(POSITIONS, history=HISTORY_FACT), 'deviation_from_mean')
    assert [s['symbol'] for s in signals] == ['110011', '600000']
    assert signals[0]['current_pct'] == 55.0
    assert signals[0]['mean_pct'] == 42.0
    assert signals[0]['delta_pct'] == 13.0
    assert signals[0]['sample_days'] == 13
    assert signals[0]['level'] == 'caution'
    assert signals[1]['delta_pct'] == -13.0


def test_deviation_only_reports_currently_held_symbols():
    fact = dict(HISTORY_FACT, means={'110011': 42.0, 'CLEARED': 30.0})
    signals = _signals_of(_report(POSITIONS, history=fact), 'deviation_from_mean')
    assert [s['symbol'] for s in signals] == ['110011']


def test_history_needs_at_least_two_samples():
    report = _report(POSITIONS, history=dict(HISTORY_FACT, sample_days=1))
    assert not _signals_of(report, 'deviation_from_mean')
    assert any(m['type'] == 'deviation_from_mean' and 'as-of' in m['reason'] for m in report['missing_signals'])


def test_fund_valuation_percentile_never_substituted_by_index():
    report = _report(POSITIONS, valuation={'index': '000300.SH', 'pe_percentile': 85})
    assert not _signals_of(report, 'fund_valuation_percentile')
    assert any(m['type'] == 'fund_valuation_percentile' and 'A′' in m['reason'] for m in report['missing_signals'])


def test_fund_valuation_percentile_signal_when_a_prime_lands():
    signal = _signals_of(_report(POSITIONS, fund_valuation=FUND_FACT), 'fund_valuation_percentile')[0]
    assert signal['symbol'] == '110011'
    assert signal['pe_percentile'] == 88
    assert signal['note'] == '估值偏高'
    assert signal['level'] == 'watch'


def test_output_has_disclaimer_and_only_three_levels():
    report = _report(
        POSITIONS,
        valuation={'index': '000300.SH', 'pe_percentile': 95},
        industry=INDUSTRY_FACT,
        history=HISTORY_FACT,
        fund_valuation=FUND_FACT,
    )
    assert report['disclaimer'] == DISCLAIMER
    assert report['as_of'] == AS_OF and report['scope'] == SCOPE
    assert {s['level'] for s in report['signals']} <= VALID_LEVELS


def test_no_directional_advice_in_output():
    """防幻觉硬约束：全量事实下也不能出现模型可自由发挥的买卖方向词。"""
    report = _report(
        POSITIONS,
        valuation={'index': '000300.SH', 'pe_percentile': 95},
        industry=INDUSTRY_FACT,
        history=HISTORY_FACT,
        fund_valuation=FUND_FACT,
    )
    payload = json.dumps(report, ensure_ascii=False)
    for word in ('买入', '卖出', '加仓', '减仓', '推荐', '应该买', '应该卖'):
        assert word not in payload, f'输出出现方向性措辞：{word}'

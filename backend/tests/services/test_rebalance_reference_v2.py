# -*- coding: utf-8 -*-
"""Q3 v2 取数层单测（D112）。

不在测试里造跨市场域的净值 / 流水表：底层取数 helper 用合成事实替换，
这里只钉住本模块的口径 —— as-of 份额 × 「≤ 当日最后已知价」的相对市值、
采样不足不出数、行业 fact 只取 csrc 主口径、A′ 未落库时个基分位返回 None。
真实取价 / 份额语义由 pnl_calendar 自己的回归网负责。
"""

from datetime import date
from types import SimpleNamespace

from app.domains.temperature.models import MarketMultiItem
from app.services.analytics import rebalance_reference_v2 as v2

DAYS = [date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)]
EPOCH = date(2026, 1, 1)


def _pos(pid, symbol):
    return SimpleNamespace(id=pid, symbol=symbol, currency='CNY', asset_type='fund')


def _patch_history(monkeypatch, positions, price_by_symbol, sample_days=DAYS, every=1):
    monkeypatch.setattr(v2, '_trading_days_between', lambda start, end: sample_days)
    monkeypatch.setattr(v2, 'SAMPLE_EVERY_N_TRADING_DAYS', every)
    monkeypatch.setattr(
        v2,
        '_as_of_shares',
        lambda db, family_id, end: ({p.id: {EPOCH: 10000} for p in positions}, {}),
    )
    monkeypatch.setattr(
        v2,
        '_collect_fund_nav',
        lambda db, start, end, codes: {sym: {d: units for d in sample_days} for sym, units in price_by_symbol.items()},
    )
    monkeypatch.setattr(v2, '_collect_price_history', lambda db, symbols, start, end: {})
    monkeypatch.setattr(v2, '_price_series_of', lambda pos, nav, prices: nav.get(pos.symbol))


def test_history_weights_are_asof_prices_not_current_prices(monkeypatch):
    positions = [_pos(1, '110011'), _pos(2, '600000')]
    _patch_history(monkeypatch, positions, {'110011': 10000, '600000': 20000})
    fact = v2.build_history_fact(object(), 1, positions)
    assert fact['sample_days'] == 3
    assert fact['means'] == {'110011': 33.33, '600000': 66.67}


def test_history_needs_two_priced_samples(monkeypatch):
    positions = [_pos(1, '110011')]
    _patch_history(monkeypatch, positions, {'110011': 10000}, sample_days=DAYS[:1])
    assert v2.build_history_fact(object(), 1, positions) is None


def test_history_without_positions_returns_none():
    assert v2.build_history_fact(object(), 1, []) is None


def test_history_without_any_price_returns_none(monkeypatch):
    positions = [_pos(1, '110011')]
    _patch_history(monkeypatch, positions, {})
    assert v2.build_history_fact(object(), 1, positions) is None


def test_industry_fact_keeps_csrc_and_coverage(monkeypatch):
    report = {
        'scheme': 'csrc',
        'scheme_label': '证监会门类',
        'coverage': {'penetrated_cny': 60.0, 'penetrated_ratio': 0.5312},
        'industries': [
            {'code': 'C', 'name': '制造业', 'value_cny': 60.0, 'ratio_of_penetrated': 0.6},
        ],
    }
    monkeypatch.setattr(v2, 'build_penetration', lambda db, family_id, scheme: report)
    fact = v2.build_industry_fact(object(), 1)
    assert fact['scheme'] == 'csrc'
    assert fact['penetrated_ratio'] == 0.5312
    assert fact['industries'][0]['name'] == '制造业'


def test_industry_fact_without_coverage_returns_none(monkeypatch):
    report = {'scheme': 'csrc', 'coverage': {'penetrated_cny': 0.0}, 'industries': []}
    monkeypatch.setattr(v2, 'build_penetration', lambda db, family_id, scheme: report)
    assert v2.build_industry_fact(object(), 1) is None


def test_industry_fact_survives_penetration_failure(monkeypatch):
    def _boom(db, family_id, scheme):
        raise RuntimeError('market domain unavailable')

    monkeypatch.setattr(v2, 'build_penetration', _boom)
    assert v2.build_industry_fact(object(), 1) is None


def test_fund_valuation_fact_only_reads_fund_item_type(db):
    db.add(
        MarketMultiItem(
            source='wind_valuation',
            item_type='fund',
            item_code='110011',
            item_name='甲基金',
            data={'pe_percentile': 88, 'valuation_date': '2026-11-11'},
            collected_at=date(2026, 11, 11),
            stale=False,
        )
    )
    db.add(
        MarketMultiItem(
            source='wind_valuation',
            item_type='index',
            item_code='110011',
            item_name='同名指数',
            data={'pe_percentile': 50},
            collected_at=date(2026, 11, 10),
            stale=False,
        )
    )
    db.commit()
    fact = v2.build_fund_valuation_fact(db, ['110011'])
    assert [i['pe_percentile'] for i in fact['items']] == [88]
    assert v2.build_fund_valuation_fact(db, []) is None

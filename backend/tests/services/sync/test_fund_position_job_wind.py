# -*- coding: utf-8 -*-
"""``fund_position`` job 的万得补充源（#2749 场内 ETF 底层持仓）。

只测**新加的那条支路**，东财主路的既有行为由 ``test_fund_position_job.py`` 覆盖。
全部替身，不联网：``wind_fund`` 的三个入口都 monkeypatch 掉。
"""

from datetime import date

import pytest

from app.services.sync.jobs import fund_position_job as mod
from app.services.sync.jobs.fund_position_job import FundPositionSyncJob


class _StubAdapter:
    """东财适配器替身：持仓与行业配置分别可控。"""

    def __init__(self, holdings=None, industry=None):
        self._holdings = holdings or {}
        self._industry = industry or {}
        self.calls = []

    def fetch_fund_top_holdings(self, code):
        self.calls.append(('holdings', code))
        return self._holdings

    def fetch_fund_industry_allocation(self, code):
        self.calls.append(('industry', code))
        return self._industry


def _wind_result(rows=2, period='2025Q2'):
    return {
        'fund_code': '510300.SH',
        'report_period': period,
        'holding_basis': 'top10',
        'rows': [
            {
                'stock_code': f'60000{index}',
                'stock_name': f'股票{index}',
                'ratio': 4.2,
                'shares': 1119.41,
                'market_value': 1577837.0,
                'rank': index + 1,
            }
            for index in range(rows)
        ],
        'alloc': {},
        'warnings': [],
    }


@pytest.fixture
def job():
    return FundPositionSyncJob(_StubAdapter(), db=None)


# ── 优先级：东财优先，只在缺口处补万得 ─────────────────────────────────


def test_eastmoney_holdings_win_and_wind_is_not_called(job, monkeypatch):
    """东财有持仓时必须原样用东财，且不请求万得（省额度、不换主源）。"""
    called = []
    monkeypatch.setattr(mod.wind_fund, 'is_available', lambda: True)
    monkeypatch.setattr(mod.wind_fund, 'fetch_fund_holdings', lambda *a, **k: called.append(a) or _wind_result())

    job.adapter = _StubAdapter(holdings={'report_period': '2025Q2', 'holdings': [{'stock_code': '600519'}]})
    out = job._fetch_data(False, ['510300.SH'])

    assert out[0]['holdings_source'] == 'eastmoney'
    assert called == [], '东财已有数据时不该再问万得'


def test_wind_fills_gap_when_eastmoney_returns_nothing(job, monkeypatch):
    """东财没有持仓明细时，用万得补齐，并把 source 标记成 wind。"""
    monkeypatch.setattr(mod.wind_fund, 'is_available', lambda: True)
    monkeypatch.setattr(mod.wind_fund, 'candidate_report_periods', lambda today: ['2025年三季报', '2025年中报'])
    monkeypatch.setattr(mod.wind_fund, 'fetch_fund_holdings', lambda code, period='': _wind_result(rows=3))

    job.adapter = _StubAdapter()
    out = job._fetch_data(False, ['510300.SH'])

    assert out[0]['holdings_source'] == 'wind'
    assert out[0]['holdings']['report_period'] == '2025Q2'
    assert out[0]['holdings']['holding_basis'] == 'top10'
    assert len(out[0]['holdings']['holdings']) == 3


def test_wind_is_skipped_when_not_configured(job, monkeypatch):
    """没配 Token 时根本不请求万得（可选组件缺失 ≠ 故障）。"""
    monkeypatch.setattr(mod.wind_fund, 'is_available', lambda: False)
    called = []
    monkeypatch.setattr(mod.wind_fund, 'fetch_fund_holdings', lambda *a, **k: called.append(1))

    job.adapter = _StubAdapter()
    job._fetch_data(False, ['510300.SH'])

    assert called == []
    assert not job.stats.get('errors'), '未配置不是错误，不该记 errors'


# ── 报告期不猜 ────────────────────────────────────────────────────────


def test_report_period_is_tried_in_candidate_order(job, monkeypatch):
    """按候选顺序试，取第一个真有数据的期次；前一期空不算错误。"""
    seen = []

    def fake_fetch(code, period=''):
        seen.append(period)
        return _wind_result(rows=1) if period == '2025年中报' else {**_wind_result(rows=0), 'rows': []}

    monkeypatch.setattr(mod.wind_fund, 'is_available', lambda: True)
    monkeypatch.setattr(
        mod.wind_fund, 'candidate_report_periods', lambda today: ['2025年三季报', '2025年中报', '2025年一季报']
    )
    monkeypatch.setattr(mod.wind_fund, 'fetch_fund_holdings', fake_fetch)

    job.adapter = _StubAdapter()
    out = job._fetch_data(False, ['510300.SH'])

    assert seen == ['2025年三季报', '2025年中报'], '命中后应停止，不再试更早的期次'
    assert out[0]['holdings']['report_period'] == '2025Q2'


def test_at_most_n_attempts(job, monkeypatch):
    """最多试 ``WIND_PERIOD_ATTEMPTS`` 期 —— 每期一次外部请求，不无限回溯。"""
    seen = []

    def always_empty(code, period=''):
        seen.append(period)
        return {'rows': [], 'report_period': period, 'holding_basis': 'top10'}

    many = [f'{year}年年报' for year in range(2025, 2010, -1)]
    monkeypatch.setattr(mod.wind_fund, 'is_available', lambda: True)
    monkeypatch.setattr(mod.wind_fund, 'candidate_report_periods', lambda today: many)
    monkeypatch.setattr(mod.wind_fund, 'fetch_fund_holdings', always_empty)

    job.adapter = _StubAdapter()
    out = job._fetch_data(False, ['510300.SH'])

    assert len(seen) == mod.WIND_PERIOD_ATTEMPTS
    assert out == [], '一期都没数据时不产出记录（不覆盖既有标量）'


def test_periodless_result_is_not_written(job, monkeypatch):
    """``report_period`` 为 None 的结果不落库 —— 版本键必须带期次，猜一个就是假数据。"""
    monkeypatch.setattr(mod.wind_fund, 'is_available', lambda: True)
    monkeypatch.setattr(mod.wind_fund, 'candidate_report_periods', lambda today: ['2025年中报'])
    monkeypatch.setattr(
        mod.wind_fund,
        'fetch_fund_holdings',
        lambda code, period='': {**_wind_result(rows=2), 'report_period': None},
    )

    job.adapter = _StubAdapter()
    assert job._fetch_data(False, ['510300.SH']) == []


# ── 失败隔离 ──────────────────────────────────────────────────────────


def test_wind_failure_does_not_break_industry_fetch(job, monkeypatch):
    """万得抛错只记 errors，不影响同一只基金的行业配置抓取。"""
    monkeypatch.setattr(mod.wind_fund, 'is_available', lambda: True)
    monkeypatch.setattr(mod.wind_fund, 'candidate_report_periods', lambda today: ['2025年中报'])

    def boom(code, period=''):
        raise RuntimeError('wind down')

    monkeypatch.setattr(mod.wind_fund, 'fetch_fund_holdings', boom)

    job.adapter = _StubAdapter(industry={'report_period': '2025Q2', 'items': [{'industry_code': 'C', 'ratio': 10}]})
    out = job._fetch_data(False, ['510300.SH'])

    assert out[0]['industry'], '行业配置仍应保留'
    assert any(e['stage'] == 'wind_holdings' for e in job.stats.get('errors', []))


def test_candidate_periods_are_ordered_recent_first():
    """真实函数（不替身）在 10 月底的候选顺序：三季报 → 中报 → 一季报 → 上年年报。"""
    periods = mod.wind_fund.candidate_report_periods(date(2026, 10, 30))[:4]
    assert periods == ['2026年三季报', '2026年中报', '2026年一季报', '2025年年报']

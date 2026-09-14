# -*- coding: utf-8 -*-
"""申万行业单源（#1431）：成交额占比分位 + BIASn 的离线用例（不打网络）。

数据源为申万宏源官网（akshare `index_hist_sw`）；本文件用 monkeypatch 注入假 ak，
纯计算函数直接喂内存 DataFrame，覆盖：占比口径、分位窗口、BIAS 三窗口、
取数失败降级（字段变化 / 单行业失败不拖垮整体 / 重试）。
"""

import pandas as pd
import pytest

from app.services.thermometer import sw_industry_source as sw


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """抖动/退避期间不真睡，避免离线用例变慢。"""
    monkeypatch.setattr(sw, '_sleep', lambda *_: None)


def _days(n: int, start: str = '2025-01-01'):
    return [d.strftime('%Y-%m-%d') for d in pd.bdate_range(start, periods=n)]


def _daily(series_map):
    """`{code: [(date, close, amount), ...]}` → 长表 [date, code, close, amount]。"""
    rows = []
    for code, items in series_map.items():
        for d, close, amount in items:
            rows.append({'date': pd.Timestamp(d), 'code': code, 'close': close, 'amount': amount})
    return pd.DataFrame(rows)


class TestComputeShareMetrics:
    def test_amount_pct_is_cross_sectional_share(self):
        days = _days(25)
        daily = _daily(
            {
                '801010': [(d, 10.0, 50.0) for d in days],
                '801030': [(d, 10.0, 30.0) for d in days],
                '801040': [(d, 10.0, 20.0) for d in days],
            }
        )
        out = sw.compute_share_metrics(daily)
        assert out['801010']['amount_pct'] == 50.0
        assert out['801030']['amount_pct'] == 30.0
        assert out['801040']['amount_pct'] == 20.0

    def test_rank_is_100_when_share_constant(self):
        days = _days(25)
        daily = _daily(
            {
                '801010': [(d, 10.0, 50.0) for d in days],
                '801030': [(d, 10.0, 50.0) for d in days],
            }
        )
        out = sw.compute_share_metrics(daily)
        # 含自身比较（x <= x[-1]）：占比恒定 → 窗口内全部命中 → 100.0
        assert out['801010']['amount_pct_rank'] == 100.0

    def test_rank_low_when_share_drops_at_end(self):
        days = _days(25)
        a = [(d, 10.0, 100.0) for d in days[:-1]] + [(days[-1], 10.0, 1.0)]
        b = [(d, 10.0, 100.0) for d in days]
        out = sw.compute_share_metrics(_daily({'801010': a, '801030': b}))
        # 最后一天占比为 25 天内最低 → 分位约 1/25 ≈ 4.0
        assert out['801010']['amount_pct_rank'] == pytest.approx(4.0, abs=0.1)

    def test_insufficient_history_is_skipped(self):
        days = _days(sw.MIN_PERIODS - 1)
        daily = _daily({'801010': [(d, 10.0, 50.0) for d in days]})
        assert sw.compute_share_metrics(daily) == {}

    def test_empty_or_none_input_returns_empty(self):
        assert sw.compute_share_metrics(pd.DataFrame()) == {}
        assert sw.compute_share_metrics(None) == {}


class TestComputeBiasMetrics:
    def test_flat_price_gives_zero_bias(self):
        days = _days(70)
        daily = _daily({'801010': [(d, 10.0, 50.0) for d in days]})
        out = sw.compute_bias_metrics(daily)
        assert out['801010']['bias6'] == 0.0
        assert out['801010']['bias20'] == 0.0
        assert out['801010']['bias60'] == 0.0

    def test_rising_price_gives_positive_bias(self):
        days = _days(70)
        row = [(d, 10.0 + i * 0.1, 50.0) for i, d in enumerate(days)]
        out = sw.compute_bias_metrics(_daily({'801010': row}))
        assert out['801010']['bias6'] > 0
        assert out['801010']['bias20'] > 0
        assert out['801010']['bias60'] > 0

    def test_falling_price_gives_negative_bias(self):
        days = _days(70)
        row = [(d, 20.0 - i * 0.1, 50.0) for i, d in enumerate(days)]
        out = sw.compute_bias_metrics(_daily({'801010': row}))
        assert out['801010']['bias20'] < 0

    def test_partial_window_yields_none_for_long_windows(self):
        days = _days(10)  # 够 bias6，不够 bias20/60
        daily = _daily({'801010': [(d, 10.0 + i * 0.1, 50.0) for i, d in enumerate(days)]})
        row = sw.compute_bias_metrics(daily)['801010']
        assert row['bias6'] is not None
        assert row['bias20'] is None
        assert row['bias60'] is None

    def test_all_windows_none_is_skipped(self):
        days = _days(3)  # 任何窗口都不足
        daily = _daily({'801010': [(d, 10.0, 50.0) for d in days]})
        assert sw.compute_bias_metrics(daily) == {}

    def test_zero_price_guards_division(self):
        days = _days(70)
        daily = _daily({'801010': [(d, 0.0, 50.0) for d in days]})
        # MA=0 → 除零保护，该行业整条不返回
        assert sw.compute_bias_metrics(daily) == {}


class _FakeAk:
    """假 akshare：按注入的清单/日线数据返回，可指定抛错的行业。"""

    def __init__(self, industries=None, hist=None, fail_codes=(), bad_fields=False):
        self._industries = industries if industries is not None else []
        self._hist = hist or {}
        self._fail = set(fail_codes)
        self._bad_fields = bad_fields

    def sw_index_first_info(self):
        return pd.DataFrame(self._industries, columns=['行业代码', '行业名称'])

    def index_hist_sw(self, symbol):
        if symbol in self._fail:
            raise RuntimeError('boom')
        if self._bad_fields:
            return pd.DataFrame({'日期': ['2026-09-14'], '收盘': [1.0]})
        rows = self._hist.get(symbol) or []
        return pd.DataFrame(rows, columns=['日期', '收盘', '成交额'])


def _patch_ak(monkeypatch, fake):
    monkeypatch.setattr('app.core.akshare_lazy.get_akshare', lambda: fake)


class TestListSwIndustries:
    def test_strips_si_suffix(self, monkeypatch):
        _patch_ak(monkeypatch, _FakeAk(industries=[['801010.SI', '农林牧渔'], ['801030.SI', '化工']]))
        out = sw.list_sw_industries()
        assert out == {'801010': '农林牧渔', '801030': '化工'}

    def test_count_mismatch_still_returns(self, monkeypatch):
        # 只有 2 个（非预期 31）→ 仅告警，仍返回，不阻塞主链路
        _patch_ak(monkeypatch, _FakeAk(industries=[['801010.SI', '农林牧渔'], ['801030.SI', '化工']]))
        assert len(sw.list_sw_industries()) == 2

    def test_failure_returns_empty(self, monkeypatch):
        class _Boom:
            def sw_index_first_info(self):
                raise RuntimeError('network down')

        _patch_ak(monkeypatch, _Boom())
        assert sw.list_sw_industries() == {}


class TestFetchSwDaily:
    def test_single_industry_failure_does_not_break_others(self, monkeypatch):
        fake = _FakeAk(
            hist={
                '801010': [['2026-09-14', 10.0, 100.0]],
                '801030': [['2026-09-14', 20.0, 200.0]],
            },
            fail_codes=('801010',),
        )
        _patch_ak(monkeypatch, fake)
        daily = sw.fetch_sw_daily(['801010', '801030'])
        assert list(daily['code'].unique()) == ['801030']
        assert daily['amount'].iloc[-1] == 200.0

    def test_retry_then_success(self, monkeypatch):
        calls = {'n': 0}

        class _Flaky(_FakeAk):
            def index_hist_sw(self, symbol):
                calls['n'] += 1
                if calls['n'] == 1:
                    raise RuntimeError('transient')
                return pd.DataFrame([['2026-09-14', 10.0, 100.0]], columns=['日期', '收盘', '成交额'])

        _patch_ak(monkeypatch, _Flaky())
        daily = sw.fetch_sw_daily(['801010'])
        assert len(daily) == 1
        assert calls['n'] == 2

    def test_field_change_is_treated_as_failure(self, monkeypatch):
        _patch_ak(monkeypatch, _FakeAk(bad_fields=True))
        daily = sw.fetch_sw_daily(['801010'])
        assert daily.empty


class TestFetchSwMetrics:
    def test_empty_when_fetch_returns_nothing(self, monkeypatch):
        _patch_ak(monkeypatch, _FakeAk(hist={}))
        assert sw.fetch_sw_metrics(codes=['801010']) == {}

    def test_merges_share_and_bias(self, monkeypatch):
        days = _days(70)
        hist = {
            '801010': [[d, 10.0 + i * 0.1, 60.0] for i, d in enumerate(days)],
            '801030': [[d, 10.0, 40.0] for d in days],
        }
        _patch_ak(monkeypatch, _FakeAk(hist=hist))
        out = sw.fetch_sw_metrics(codes=['801010', '801030'])
        assert out['801010']['amount_pct'] == 60.0
        assert out['801010']['amount_pct_rank'] is not None
        assert out['801010']['bias6'] > 0
        assert out['801030']['bias20'] == 0.0

    def test_never_raises(self, monkeypatch):
        monkeypatch.setattr(sw, 'fetch_sw_daily', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
        assert sw.fetch_sw_metrics(codes=['801010']) == {}

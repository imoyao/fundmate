# -*- coding: utf-8 -*-
"""腾讯日线取数（adapters/direct_feeds）单元测试：#870-A 引入。

只测纯逻辑（字段解析 / 分页拼接 / 去重 / 提前终止），**不打真实网络**：
模块内的 `fetch_kline_tencent` 与 `requests.get` 被替换成预设页。
"""

from datetime import date

import pytest

from app.services.adapters import direct_feeds


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """分页间的礼貌 sleep 在测试里必须归零，否则 16 页会把用例拖成分钟级。"""
    monkeypatch.setattr(direct_feeds.time, 'sleep', lambda *_: None)


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _page_fetcher(pages, calls):
    """按调用次序返回预设页；超出预设返回空页（模拟源侧耗尽）。"""

    def _fake(symbol, start, end, count=800, timeout=12, **kwargs):
        calls.append(end)
        idx = len(calls) - 1
        return pages[idx] if idx < len(pages) else []

    return _fake


class TestParseKline:
    def test_close_is_third_field(self, monkeypatch):
        """腾讯字段序为 [日期, 开, 收, 高, 低, 量]：取 x[2] 为收盘（已与东财核对）。"""
        payload = {
            'data': {
                'sh000300': {
                    'day': [
                        ['2026-09-30', '4356.800', '4357.620', '4368.610', '4341.880', '162949626'],
                    ]
                }
            }
        }
        monkeypatch.setattr(direct_feeds.requests, 'get', lambda *a, **k: _FakeResp(payload))
        rows = direct_feeds.fetch_kline_tencent('000300.SH', date(2026, 9, 1), date(2026, 9, 30))
        assert rows == [('2026-09-30', 4357.62)]

    def test_malformed_rows_are_skipped(self, monkeypatch):
        payload = {
            'data': {
                'sh000300': {
                    'day': [
                        ['2026-09-30', '4356.8', '4357.62', '4368.6', '4341.8', '1'],
                        ['bad'],  # 列数不足
                        ['2026-09-29', 'x', 'y'],  # 收盘不可转 float
                    ]
                }
            }
        }
        monkeypatch.setattr(direct_feeds.requests, 'get', lambda *a, **k: _FakeResp(payload))
        rows = direct_feeds.fetch_kline_tencent('000300.SH', date(2026, 9, 1), date(2026, 9, 30))
        assert rows == [('2026-09-30', 4357.62)]

    def test_qfqday_key_also_accepted(self, monkeypatch):
        """宽基指数落在 `day`，ETF/股票可能在 `qfqday`——两者都要认。"""
        payload = {'data': {'sh510300': {'qfqday': [['2026-09-30', '4.0', '4.123', '4.2', '3.9', '9']]}}}
        monkeypatch.setattr(direct_feeds.requests, 'get', lambda *a, **k: _FakeResp(payload))
        rows = direct_feeds.fetch_kline_tencent('510300.SH', date(2026, 9, 1), date(2026, 9, 30))
        assert rows == [('2026-09-30', 4.123)]

    def test_network_failure_returns_empty(self, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError('RemoteDisconnected')

        monkeypatch.setattr(direct_feeds.requests, 'get', boom)
        assert direct_feeds.fetch_kline_tencent('000300.SH', date(2026, 9, 1), date(2026, 9, 30)) == []


class TestPagination:
    def test_paginates_until_source_exhausted(self, monkeypatch):
        pages = [
            [('2026-09-30', 3.0), ('2026-09-29', 2.0)],
            [('2020-01-02', 1.5), ('2020-01-01', 1.0)],
            [],  # 源侧耗尽
        ]
        calls = []
        monkeypatch.setattr(direct_feeds, 'fetch_kline_tencent', _page_fetcher(pages, calls))

        rows = direct_feeds.fetch_daily_tencent('000300.SH')

        assert rows == [
            ('2020-01-01', 1.0),
            ('2020-01-02', 1.5),
            ('2026-09-29', 2.0),
            ('2026-09-30', 3.0),
        ], '必须按日期升序返回'
        assert len(calls) == 3, '第三页取空后应停止翻页'

    def test_stops_early_when_start_date_reached(self, monkeypatch):
        pages = [
            [('2026-09-30', 3.0), ('2025-10-01', 2.0)],
            [('2025-09-30', 1.0)],
        ]
        calls = []
        monkeypatch.setattr(direct_feeds, 'fetch_kline_tencent', _page_fetcher(pages, calls))

        rows = direct_feeds.fetch_daily_tencent('000300.SH', start_date=date(2025, 10, 1))

        assert len(calls) == 1, '首页首日已 <= start_date，不该再翻第二页'
        assert rows[0] == ('2025-10-01', 2.0)

    def test_incremental_first_page_starts_at_start_date(self, monkeypatch):
        """增量首页必须**按 start_date 定界**，不能沿用固定的 page_span。

        沿用 page_span 会让「近 12 月」变成「近 3.2 年 / 800 条」（2026-10-01 真机实测），
        与韭圈儿侧的 12 月口径不一致，且每次白写数百行 upsert。
        """
        seen = []

        def _fake(symbol, start, end, count=800, timeout=12, **kwargs):
            seen.append((start, end))
            return [('2025-10-01', 1.0), ('2026-09-30', 2.0)]

        monkeypatch.setattr(direct_feeds, 'fetch_kline_tencent', _fake)
        rows = direct_feeds.fetch_daily_tencent('000300.SH', start_date=date(2025, 10, 1))

        assert seen == [(date(2025, 10, 1), date.today())]
        assert len(seen) == 1, '首页即已覆盖到 start_date，不该再翻页'
        assert rows[0][0] == '2025-10-01'

    def test_no_progress_guard_stops_immediately(self, monkeypatch):
        """源侧首日不前进时必须立刻收手，不能空转翻满 max_pages。"""
        same = [('2026-09-30', 3.0)]
        calls = []
        monkeypatch.setattr(direct_feeds, 'fetch_kline_tencent', _page_fetcher([same, same, same], calls))

        rows = direct_feeds.fetch_daily_tencent('000300.SH')

        assert rows == [('2026-09-30', 3.0)]
        assert len(calls) == 2, '第二页首日未推进 → 收手'

    def test_overlapping_boundary_day_is_deduped(self, monkeypatch):
        pages = [
            [('2026-09-30', 3.0), ('2026-09-29', 2.0)],
            [('2026-09-29', 2.0), ('2026-09-28', 1.0)],  # 边界日与上页重叠
            [],
        ]
        calls = []
        monkeypatch.setattr(direct_feeds, 'fetch_kline_tencent', _page_fetcher(pages, calls))

        rows = direct_feeds.fetch_daily_tencent('000300.SH')

        assert rows == [('2026-09-28', 1.0), ('2026-09-29', 2.0), ('2026-09-30', 3.0)]

    def test_max_pages_caps_requests(self, monkeypatch):
        """即使源侧一直有数据，翻页数也不得超过 max_pages（防呆）。"""
        calls = []

        def always(wsymbol, start, end, count=800, timeout=12, **kwargs):
            calls.append(end)
            return [(end.isoformat(), 1.0)]

        monkeypatch.setattr(direct_feeds, 'fetch_kline_tencent', always)
        direct_feeds.fetch_daily_tencent('000300.SH', max_pages=4)
        assert len(calls) == 4


class TestSymbolNormalization:
    @pytest.mark.parametrize(
        ('given', 'expected'),
        [
            ('000300.SH', 'sh000300'),
            ('399006.SZ', 'sz399006'),
            ('sh000001', 'sh000001'),
        ],
    )
    def test_tencent_symbol(self, given, expected):
        assert direct_feeds._tencent_symbol(given) == expected

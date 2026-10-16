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


class TestCsindexDaily:
    """中证官网日线（#167）。**不打真实网络**：`requests.get` 换成预设响应。"""

    def _patch(self, monkeypatch, payload):
        calls = []

        def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
            calls.append(dict(params or {}))
            return _FakeResp(payload)

        monkeypatch.setattr(direct_feeds.requests, 'get', fake_get)
        return calls

    def test_parses_and_sorts_ascending(self, monkeypatch):
        # 源侧给出「YYYYMMDD」；故意反序，验证函数自己排序
        payload = {
            'code': '200',
            'data': [
                {'tradeDate': '20261013', 'close': 3024.95},
                {'tradeDate': '20230901', 'close': 3100.0},
            ],
        }
        self._patch(monkeypatch, payload)
        rows = direct_feeds.fetch_daily_csindex('932000')
        assert rows == [('2023-09-01', 3100.0), ('2026-10-13', 3024.95)]

    def test_accepts_dashed_date_form(self, monkeypatch):
        """容错 'YYYY-MM-DD' 形态——源侧日后若改格式，不该静默变成 0 条。"""
        payload = {'data': [{'tradeDate': '2026-10-13', 'close': 3024.95}]}
        self._patch(monkeypatch, payload)
        assert direct_feeds.fetch_daily_csindex('932000') == [('2026-10-13', 3024.95)]

    def test_empty_data_returns_empty_list(self, monkeypatch):
        """未收录的代码源侧返回空 data（不报错）⇒ 静默返回 []，不抛异常阻断同步。"""
        self._patch(monkeypatch, {'code': '200', 'data': []})
        assert direct_feeds.fetch_daily_csindex('999999') == []

    def test_skips_malformed_rows(self, monkeypatch):
        payload = {
            'data': [
                {'tradeDate': '20261013', 'close': 3024.95},
                {'tradeDate': None, 'close': 1.0},
                {'tradeDate': '20261012', 'close': None},
                {'tradeDate': '20261011', 'close': 'not-a-number'},
                'not-a-dict',
            ]
        }
        self._patch(monkeypatch, payload)
        assert direct_feeds.fetch_daily_csindex('932000') == [('2026-10-13', 3024.95)]

    def test_http_failure_degrades_silently(self, monkeypatch):
        """通道异常一律降级为空列表（best-effort，与其余源一致）。"""

        def boom(*args, **kwargs):
            raise RuntimeError('down')

        monkeypatch.setattr(direct_feeds.requests, 'get', boom)
        assert direct_feeds.fetch_daily_csindex('932000') == []

    def test_passes_naked_code_and_date_range(self, monkeypatch):
        calls = self._patch(monkeypatch, {'data': [{'tradeDate': '20261013', 'close': 1.0}]})
        direct_feeds.fetch_daily_csindex('932000', start_date=date(2023, 8, 1), end_date=date(2026, 10, 14))
        assert calls[0]['indexCode'] == '932000'
        assert calls[0]['startDate'] == '20230801'
        assert calls[0]['endDate'] == '20261014'

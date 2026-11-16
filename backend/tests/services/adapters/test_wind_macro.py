# -*- coding: utf-8 -*-
"""Wind EDB 宏观适配器：两个能力的载荷解析、参数名、宽容度。

全部替身，不联网、不读凭据。真机契约见 ``wind_edb`` 模块头（2026-11-16 复核）：
search 回指标清单、query 回 ``metrics[].meta`` + ``date[]`` / ``value[]``。

**本文件存在理由**：宏观工具把「检索 → 选择 → 取数」封在一次调用里，解析层一旦宽容过头
（字段缺失当空、形状漂移不报错），上层会拿到「找到指标但没有数据」的假象——
与 #1502 那次静默降级同型。
"""

import json
from datetime import date

import pytest

from app.services.adapters import wind_macro


class _StubTransport:
    """按调用顺序吐预设文本；文本不足时重复最后一条。"""

    def __init__(self, texts):
        self._texts = list(texts)
        self.calls = []

    def call_tool(self, tool, arguments, token=None):
        self.calls.append({'tool': tool, 'arguments': arguments, 'token': token})
        text = self._texts.pop(0) if len(self._texts) > 1 else self._texts[0]
        return text


class _StubProvider:
    name = 'wind'

    def __init__(self, transport):
        self.transport = transport

    def scope_of(self, capability):
        return 'public_market'

    def tool_for(self, capability):
        return {
            'edb_search': 'economic_search_indicator',
            'edb_query': 'economic_query_indicator_series',
        }[capability]

    def build_transport(self, post):
        return self.transport


@pytest.fixture
def stub(monkeypatch):
    """装上替身 provider；返回 (install 工厂)。"""

    def _install(*payloads):
        texts = [p if isinstance(p, str) else json.dumps(p, ensure_ascii=False) for p in payloads]
        provider = _StubProvider(_StubTransport(texts))
        monkeypatch.setattr(wind_macro, 'get_provider', lambda name: provider)
        monkeypatch.setattr(wind_macro, 'resolve_token', lambda *a, **k: 'stub-token')
        monkeypatch.setattr(wind_macro, '_post_factory', lambda *a, **k: None)
        return provider

    return _install


# ── search_indicators ────────────────────────────────────────────────────
def test_search_parses_meta_wrapped_and_flat_entries(stub):
    """实测在 ``meta`` 下；search 侧可能平铺——两种都要认，否则一半指标查不到名。"""
    stub(
        {
            'metrics': [
                {'meta': {'name': '中国:GDP:不变价:当季同比', 'code': 'M0039354', 'freq': '季'}},
                {'name': '制造业PMI', 'code': 'M0017', 'freq': '月'},
                {'name': '   ', 'code': 'X'},  # 无名条目：下一步没法取数，必须丢
            ]
        }
    )

    rows = wind_macro.search_indicators('中国GDP')

    assert rows == [
        {'name': '中国:GDP:不变价:当季同比', 'code': 'M0039354', 'freq': '季'},
        {'name': '制造业PMI', 'code': 'M0017', 'freq': '月'},
    ]


def test_search_sends_question_verbatim(stub):
    """问法原样上行：上游检索是自然语言语义匹配，改写问法等于换了检索词。"""
    provider = stub({'metrics': []})

    wind_macro.search_indicators('中国GDP当季同比')

    assert provider.transport.calls[0]['arguments'] == {'question': '中国GDP当季同比'}
    assert provider.transport.calls[0]['tool'] == 'economic_search_indicator'


def test_search_empty_metrics_is_empty_list(stub):
    stub({'metrics': []})
    assert wind_macro.search_indicators('不存在的东西') == []


def test_search_non_json_raises(stub):
    stub(['not json'])
    with pytest.raises(wind_macro.McpBadResponse):
        wind_macro.search_indicators('GDP')


def test_search_metrics_wrong_shape_raises(stub):
    """``metrics`` 是 dict（而非 list）= 上游形状漂移，必须报错而不是当空。"""
    stub({'metrics': {'name': 'x'}})
    with pytest.raises(wind_macro.McpBadResponse):
        wind_macro.search_indicators('GDP')


# ── fetch_series ─────────────────────────────────────────────────────────
def test_fetch_sends_upstream_date_param_names(stub):
    """上游要 ``startDate``/``endDate``（``beginDate`` 已废弃，见 #3145）。"""
    provider = stub({'metrics': []})

    wind_macro.fetch_series('中国:GDP:不变价:当季同比', date(2024, 1, 1), date(2026, 11, 16))

    args = provider.transport.calls[0]['arguments']
    assert args == {
        'question': '中国:GDP:不变价:当季同比',
        'startDate': '2024-01-01',
        'endDate': '2026-11-16',
    }
    assert 'beginDate' not in args


def test_fetch_keeps_all_same_family_series(stub):
    """同族多条**全部保留**：哪一条是用户要的，只有上层（拿着原话）判得准。"""
    stub(
        {
            'metrics': [
                {
                    'meta': {'name': '中国:GDP:不变价:当季同比', 'freq': '季', 'unit': '%'},
                    'date': ['20260930'],
                    'value': ['4.8'],
                },
                {'meta': {'name': '中国:GDP:现价:当季值', 'freq': '季'}, 'date': ['20260930'], 'value': ['334193']},
            ]
        }
    )

    rows = wind_macro.fetch_series('中国:GDP', date(2026, 1, 1), date(2026, 11, 16))

    assert [r['name'] for r in rows] == ['中国:GDP:不变价:当季同比', '中国:GDP:现价:当季值']
    assert rows[0]['points'] == {date(2026, 9, 30): 4.8}
    assert rows[0]['unit'] == '%'


def test_fetch_drops_out_of_range_and_unparsable_points(stub):
    """窗口外丢弃；空值 / 坏日期跳过（**不补 0**：0 会被叙事读成真值）。"""
    stub(
        {
            'metrics': [
                {
                    'meta': {'name': 'X'},
                    'date': ['20251231', '20260102', '20260103', 'bad', '20260104'],
                    'value': ['1', '', '2', '3', '--'],
                }
            ]
        }
    )

    rows = wind_macro.fetch_series('X', date(2026, 1, 1), date(2026, 1, 31))

    assert rows[0]['points'] == {date(2026, 1, 3): 2.0}


def test_fetch_skips_series_without_points(stub):
    """有名字但窗口内一个点都没有的条目直接丢：回一个空序列只会让上层误判「有数据」。"""
    stub({'metrics': [{'meta': {'name': 'X'}, 'date': [], 'value': []}]})
    assert wind_macro.fetch_series('X', date(2026, 1, 1), date(2026, 1, 31)) == []


# ── normalize ────────────────────────────────────────────────────────────
def test_normalize_strips_separators_and_case():
    assert wind_macro.normalize('中国:GDP：不变价 · 当季同比') == wind_macro.normalize('中国 GDP不变价当季同比')
    assert wind_macro.normalize(None) == ''

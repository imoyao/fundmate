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

from app.services.adapters import macro_cache, wind_macro
from app.services.mcp.errors import McpBillingError


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


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch, tmp_path):
    """本模块新增的复用缓冲层是**跨调用状态**：每个用例一个独立目录，避免互相喂数据。

    不隔的后果很具体：``test_fetch_drops_out_of_range_and_unparsable_points`` 会为 'X'
    写入缓存，紧接着 ``test_fetch_skips_series_without_points`` 就命中它拿到非空——
    两个用例单独跑都绿、一起跑红。
    """
    monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path))


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


# ── 复用缓冲层（成本红线） ────────────────────────────────────────────────
def test_fetch_reuses_cache_and_marks_hit(stub):
    """同指标同窗口第二次不再打上游——每打一次都扣积分，这是硬成本。"""
    provider = stub({'metrics': [{'meta': {'name': 'CPI', 'freq': '月'}, 'date': ['20261031'], 'value': ['0.7']}]})

    first = wind_macro.fetch_series('CPI', date(2026, 1, 1), date(2026, 11, 16))
    second = wind_macro.fetch_series('CPI', date(2026, 1, 1), date(2026, 11, 16))

    assert len(provider.transport.calls) == 1, '第二次必须命中缓存，不能重复计费'
    assert 'cache' not in first[0], '首次是实时数据，不该被标记成缓存'
    assert second[0]['cache'] == 'hit'
    assert second[0]['points'] == {date(2026, 10, 31): 0.7}


def test_fetch_falls_back_to_stale_when_billing_fails(stub, monkeypatch):
    """额度耗尽时回过期缓存并标 ``stale``：比抛错让用户看到「结构异常」有用得多。"""
    stub({'metrics': [{'meta': {'name': 'CPI', 'freq': '月'}, 'date': ['20261031'], 'value': ['0.7']}]})
    wind_macro.fetch_series('CPI', date(2026, 1, 1), date(2026, 11, 16))
    monkeypatch.setattr(macro_cache, 'ttl_seconds', lambda freq: -1)  # 让缓存立刻算过期

    def _billing(*args, **kwargs):
        raise McpBillingError('账户积分余额不足')

    monkeypatch.setattr(wind_macro, '_call', _billing)

    got = wind_macro.fetch_series('CPI', date(2026, 1, 1), date(2026, 11, 16))

    assert got[0]['cache'] == 'stale'
    assert got[0]['fetched_at'], 'stale 必须带采集时间，叙事要能交代数据时点'
    assert got[0]['points'] == {date(2026, 10, 31): 0.7}


def test_fetch_without_cache_keeps_calling_upstream(stub):
    """``use_cache=False`` 必须真的每次都打——排障时需要一个「确认上游现状」的开关。"""
    provider = stub({'metrics': [{'meta': {'name': 'CPI'}, 'date': ['20261031'], 'value': ['0.7']}]})

    wind_macro.fetch_series('CPI', date(2026, 1, 1), date(2026, 11, 16), use_cache=False)
    wind_macro.fetch_series('CPI', date(2026, 1, 1), date(2026, 11, 16), use_cache=False)

    assert len(provider.transport.calls) == 2


def test_search_reuses_cache_for_same_question(stub):
    """检索也计费；同一问句在 Agent 重试 / 多轮里重复出现，命中缓存即省一次。"""
    provider = stub({'metrics': [{'meta': {'name': '中国:GDP:不变价:当季同比', 'freq': '季'}}]})

    wind_macro.search_indicators('中国GDP同比')
    again = wind_macro.search_indicators('中国GDP同比')

    assert len(provider.transport.calls) == 1
    assert again[0]['cache'] == 'hit'


# ── normalize ────────────────────────────────────────────────────────────
def test_normalize_strips_separators_and_case():
    assert wind_macro.normalize('中国:GDP：不变价 · 当季同比') == wind_macro.normalize('中国 GDP不变价当季同比')
    assert wind_macro.normalize(None) == ''

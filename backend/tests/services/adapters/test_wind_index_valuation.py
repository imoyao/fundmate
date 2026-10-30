# -*- coding: utf-8 -*-
"""指数估值适配器（Wind 指数域，S6）：口径守卫 + 两张表归并。

全部替身，不联网。报文形状取自 2026-10-30 真机返回（见
:mod:`app.services.adapters.wind_index_valuation` 模块 docstring 的采样记录）。
"""

import json

import pytest

from app.services.adapters import wind_index_valuation as wiv


def _table(columns, rows):
    return {'columns': [{'name': c, 'type': 'number'} for c in columns], 'rows': rows}


def _payload(*tables):
    return {'data': {'data': list(tables)}, 'error': None}


class _StubTransport:
    """记录问句，按预设 payload 回包（可给多张表）。"""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def call_tool(self, tool, arguments, token=None):
        self.calls.append({'tool': tool, 'arguments': arguments, 'token': token})
        return json.dumps(self.payload, ensure_ascii=False)


class _StubProvider:
    name = 'wind_index'

    def __init__(self, payload):
        self.transport = _StubTransport(payload)

    def scope_of(self, capability):
        return 'public_market'

    def build_transport(self, post):
        return self.transport

    def tool_for(self, capability):
        assert capability == wiv.CAPABILITY
        return 'get_index_fundamentals'

    def map_args(self, capability, **kwargs):
        return kwargs

    def extract(self, text, columns=None):
        payload = json.loads(text)
        out = []
        for node in payload['data']['data']:
            names = [c['name'] for c in node.get('columns') or []]
            out.extend(dict(zip(names, row)) for row in node.get('rows') or [])
        return out


def _run(payload, entities=('000300.SH',), **kwargs):
    provider = _StubProvider(payload)
    rows = wiv.fetch_index_valuations(list(entities), provider=provider, transport=provider.transport, **kwargs)
    return rows, provider


# ── 问句守卫：不许出现「加权」 ────────────────────────────────────────


def test_question_never_says_jiaquan():
    """问句里不许出现「加权」。

    实测同一指数问「加权市盈率」在多标的场景下返回 1917.8866（放大百倍、单位标 %），
    而问「市盈率」返回 12.87。形态不稳定，故从根本上不用那个词。
    """
    payload = _payload(_table(['Wind代码', '证券简称', '最新市盈率'], [['000300.SH', '沪深300', 12.87]]))
    _, provider = _run(payload)
    question = provider.transport.calls[0]['arguments']['question']
    assert '加权' not in question
    assert '市盈率' in question


def test_percentile_question_asks_for_percentile():
    payload = _payload(_table(['Wind代码', '证券简称', '最新市盈率'], [['000300.SH', '沪深300', 12.87]]))
    _, provider = _run(payload, with_percentile=True)
    assert '分位数' in provider.transport.calls[0]['arguments']['question']


# ── 两张表归并 ────────────────────────────────────────────────────────


def test_valuation_and_percentile_tables_merge_into_one_row():
    """上游把估值与分位当**两张并列表**返回；必须归并成一行，不能变成两行。

    不归并的后果：下游会把同一天同一个指数当成两个指数，或「只有分位没有估值」。
    """
    valuation = _table(
        ['Wind代码', '证券简称', '最新市盈率', '最新市净率', '最新股息率', '日期'],
        [['000300.SH', '沪深300', 12.8628, 1.3628, 3.0129, '20261030']],
    )
    percentile = _table(
        ['Wind代码', '证券简称', '历史每日市盈率', '日期', '最新市盈率在历史中的分位数'],
        [['000300.SH', '沪深300', 44.5866, '2026-10-30', 44.7012]],
    )
    rows, _ = _run(_payload(valuation, percentile), with_percentile=True)
    assert len(rows) == 1
    row = rows[0]
    assert row['pe'] == pytest.approx(12.8628)
    assert row['pb'] == pytest.approx(1.3628)
    assert row['dividend_yield'] == pytest.approx(3.0129)
    assert row['pe_percentile'] == pytest.approx(44.7012)


def test_percentile_column_does_not_leak_into_pe():
    """分位列名含「最新市盈率」子串，不排除会把百分位当成 PE。

    实测事故现场：沪深300 的 pe 与 pe_percentile 都曾等于 44.5866。
    """
    percentile_only = _table(
        ['Wind代码', '证券简称', '历史每日市盈率', '最新市盈率在历史中的分位数'],
        [['000300.SH', '沪深300', 44.5866, 44.7012]],
    )
    rows, _ = _run(_payload(percentile_only), with_percentile=True)
    # 只有分位、没有任何估值的三项 → 不算有效估值行
    assert rows == []


def test_date_formats_are_normalized():
    """两张表的日期格式不同（``20261030`` vs ``2026-10-30``），必须归一。"""
    payload = _payload(
        _table(['Wind代码', '证券简称', '最新市盈率', '日期'], [['000300.SH', '沪深300', 12.87, '20261030']])
    )
    rows, _ = _run(payload)
    assert rows[0]['date'] == '2026-10-30'


# ── 区间守卫 ──────────────────────────────────────────────────────────


def test_out_of_range_pe_is_dropped_not_clamped():
    """1917.8866 这种放大百倍的值必须**拒收**，不能夹到 1000 也不能写进去。

    同一行的 PB / 股息率仍保留 —— 一个坏字段不该让整行消失。
    """
    payload = _payload(
        _table(
            ['Wind代码', '证券简称', '指数加权市盈率', '最新市净率', '最新股息率', '日期'],
            [['000300.SH', '沪深300', 1917.8866, 1.3628, 3.0129, '20261030']],
        )
    )
    rows, _ = _run(payload)
    assert len(rows) == 1
    assert rows[0]['pe'] is None, '超界 PE 必须被丢弃'
    assert rows[0]['pb'] == pytest.approx(1.3628), '同一行的其它字段不该受影响'


def test_row_without_any_valid_valuation_is_not_returned():
    payload = _payload(_table(['Wind代码', '证券简称', '交易时间'], [['000300.SH', '沪深300', '20261030 10:28']]))
    rows, _ = _run(payload)
    assert rows == []


def test_empty_entities_makes_no_call():
    provider = _StubProvider(_payload())
    assert wiv.fetch_index_valuations([], provider=provider, transport=provider.transport) == []
    assert provider.transport.calls == []


# ── 可用性判据 ────────────────────────────────────────────────────────


def test_is_available_requires_only_token(monkeypatch):
    """判据只有 Token：地址有已实测的默认值，不再要求配置 URL。"""
    monkeypatch.setattr(wiv, 'is_configured', lambda provider: True)
    monkeypatch.delenv('WIND_INDEX_MCP_URL', raising=False)
    assert wiv.is_available() is True

    monkeypatch.setattr(wiv, 'is_configured', lambda provider: False)
    assert wiv.is_available() is False

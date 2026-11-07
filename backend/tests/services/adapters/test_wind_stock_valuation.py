# -*- coding: utf-8 -*-
"""个股估值分位适配器（#2944）：固定问句 + 列名漂移 + 两表归并 + 分块 + 失败不吞。

全部替身，不联网。报文形状取自 2026-11-07 真机（问句 A），列名变体取自同批
B / D 问句——它们虽被弃用，但正好是「上游换列名」的回归样本。
"""

import json

import pytest

from app.services.adapters import wind_stock_valuation as wsv
from app.services.mcp import get_provider
from app.services.mcp.credentials import DataScope


def _table(columns, rows):
    return {'columns': [{'name': c, 'type': 'number'} for c in columns], 'rows': rows}


def _payload(*tables):
    return {'data': {'data': list(tables)}, 'error': None}


PE_TABLE = _table(
    [
        'Wind代码',
        '证券简称',
        '过去5年市盈率',
        '日期',
        '过去5年市净率',
        '过去5年市盈率序号',
        '过去5年市盈率最大序号',
        '最新市盈率在过去5年的分位数',
    ],
    [['600519.SH', '贵州茅台', 22.1075, '2026-11-06', 6.6974, 398, 1212, 32.7828]],
)
PB_TABLE = _table(
    [
        'Wind代码',
        '证券简称',
        '过去5年市盈率',
        '日期',
        '过去5年市净率',
        '过去5年市净率序号',
        '过去5年市净率最大序号',
        '最新市净率在过去5年的分位数',
    ],
    [['600519.SH', '贵州茅台', 22.1075, '2026-11-06', 6.6974, 102, 1212, 8.3402]],
)


class _StubTransport:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def call_tool(self, tool, arguments, token=None):
        self.calls.append({'tool': tool, 'arguments': arguments, 'token': token})
        payload = self.payloads.pop(0) if self.payloads else RuntimeError('上游炸了')
        if isinstance(payload, Exception):
            raise payload
        return json.dumps(payload, ensure_ascii=False)


class _StubProvider:
    name = 'wind_stock'

    def __init__(self, payloads):
        self.transport = _StubTransport(payloads)

    def scope_of(self, capability):
        return DataScope.PUBLIC_MARKET

    def build_transport(self, post):
        return self.transport

    def tool_for(self, capability):
        assert capability == wsv.CAPABILITY
        return 'get_stock_fundamentals'

    def map_args(self, capability, **kwargs):
        return kwargs

    def extract(self, text, columns=None):
        payload = json.loads(text)
        out = []
        for node in payload['data']['data']:
            names = [c['name'] for c in node.get('columns') or []]
            out.extend(dict(zip(names, row)) for row in node.get('rows') or [])
        return out


def _run(payloads, codes=('600519.SH',)):
    provider = _StubProvider(payloads)
    rows = wsv.fetch_stock_valuations(list(codes), provider=provider, transport=provider.transport)
    return rows, provider


# ── 能力登记 ────────────────────────────────────────────────────────────


def test_capability_registered_on_stock_domain():
    """下游按能力名取数，不写死工具名；登记后 scope 自动是 PUBLIC_MARKET。"""
    provider = get_provider('wind_stock')
    assert provider.tool_for('stock_valuation') == 'get_stock_fundamentals'
    assert provider.scope_of('stock_valuation') == DataScope.PUBLIC_MARKET


# ── 固定问句 ────────────────────────────────────────────────────────────


def test_question_is_fixed_and_asks_both_percentiles():
    """问句不许带「加权」等修饰词，也不许只问 PE（上游会只回一张表）。"""
    _, provider = _run([_payload(PE_TABLE, PB_TABLE)])
    question = provider.transport.calls[0]['arguments']['question']
    assert question == wsv.QUESTION_TEMPLATE.format(codes='600519.SH')
    assert '加权' not in question
    assert '过去5年' in question
    assert '分位数' in question
    assert '市盈率' in question and '市净率' in question


# ── 两表归并 / 列名漂移 ─────────────────────────────────────────────────


def test_pe_and_pb_tables_merge_into_one_row():
    """PE 分位与 PB 分位在两张并列表中，按 Wind代码 归并，不能变成两行。"""
    rows, _ = _run([_payload(PE_TABLE, PB_TABLE)])
    assert len(rows) == 1
    row = rows[0]
    assert row['wind_code'] == '600519.SH'
    assert row['name'] == '贵州茅台'
    assert row['date'] == '2026-11-06'
    assert row['pe'] == pytest.approx(22.1075)
    assert row['pb'] == pytest.approx(6.6974)
    assert row['pe_percentile'] == pytest.approx(32.7828)
    assert row['pb_percentile'] == pytest.approx(8.3402)
    assert row['window'] == '5y'
    assert row['source'] == wsv.SOURCE


def test_column_drift_near5y_wording_still_parsed():
    """上游把「过去5年」写成「近5年」时仍要认列（探针里的 D 问句形态）。"""
    pe = _table(
        ['Wind代码', '证券简称', '最新市盈率', '日期', '近5年的市净率', '最新市盈率在近5年的分位数'],
        [['600519.SH', '贵州茅台', 22.1075, '20261106', 6.6974, 32.7828]],
    )
    pb = _table(
        ['Wind代码', '证券简称', '近5年的市盈率', '日期', '最新市净率', '最新市净率在近5年的分位数'],
        [['600519.SH', '贵州茅台', 22.1075, '2026-11-06', 6.6974, 8.3402]],
    )
    rows, _ = _run([_payload(pe, pb)])
    assert len(rows) == 1
    assert rows[0]['pe_percentile'] == pytest.approx(32.7828)
    assert rows[0]['pb_percentile'] == pytest.approx(8.3402)
    assert rows[0]['date'] == '2026-11-06'


def test_percentile_column_is_never_read_as_current_pe():
    """分位列同时含「市盈率」，排除失效会把百分位当成 PE（同族 #2749 教训）。"""
    rows, _ = _run([_payload(PE_TABLE)])
    assert rows[0]['pe'] == pytest.approx(22.1075)
    assert rows[0]['pe'] != rows[0]['pe_percentile']


# ── 分块 / 数值守卫 ────────────────────────────────────────────────────


def test_six_codes_are_chunked_and_merged():
    codes = [f'60000{i}.SH' for i in range(6)]

    def three_rows(chunk):
        pe = _table(['Wind代码', '过去5年市盈率', '最新市盈率在过去5年的分位数'], [[c, 10.0, 50.0] for c in chunk])
        pb = _table(['Wind代码', '过去5年市净率', '最新市净率在过去5年的分位数'], [[c, 1.0, 20.0] for c in chunk])
        return _payload(pe, pb)

    rows, provider = _run([three_rows(codes[:3]), three_rows(codes[3:])], codes)
    assert len(provider.transport.calls) == 2
    assert len(rows) == 6
    assert {r['wind_code'] for r in rows} == set(codes)


def test_out_of_range_percentile_is_rejected_not_clamped():
    bad = _table(
        ['Wind代码', '过去5年市盈率', '最新市盈率在过去5年的分位数'],
        [['600519.SH', 22.1075, 150.0]],
    )
    rows, _ = _run([_payload(bad)])
    assert rows[0]['pe_percentile'] is None
    assert rows[0]['pe'] == pytest.approx(22.1075)


def test_rows_without_wind_code_are_skipped():
    bad = _table(['证券简称', '过去5年市盈率'], [['无名', 22.1075]])
    rows, _ = _run([_payload(bad, PE_TABLE)])
    assert len(rows) == 1
    assert rows[0]['wind_code'] == '600519.SH'


def test_empty_codes_never_call_upstream():
    rows, provider = _run([], ())
    assert rows == []
    assert provider.transport.calls == []


def test_upstream_failure_is_not_swallowed_into_no_data():
    with pytest.raises(RuntimeError, match='上游炸了'):
        _run([RuntimeError('上游炸了')])

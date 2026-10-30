# -*- coding: utf-8 -*-
"""万得股票档案适配器（#2749）：代码归一、批量回填、转债解析、失败降级。

全部替身，不联网、不读真实凭据。真机报文形状见 :mod:`app.services.adapters.wind_stock`
的模块 docstring（2026-10-30 采样）。
"""

import json

import pytest

from app.services.adapters import wind_stock


class _StubTransport:
    """按**问句里出现的代码**回行，并且故意倒序返回。

    两件事都是实测特性：上游只回问句里问到的标的；返回顺序与请求顺序不一致。
    替身照抄这两点，才能证明「按 Wind代码 回填」而不是「按行序配」。
    """

    def __init__(self, universe):
        #: wind_code -> 行（原始 cells）
        self.universe = universe
        self.calls = []

    def call_tool(self, tool, arguments, token=None):
        self.calls.append({'tool': tool, 'arguments': arguments, 'token': token})
        question = arguments.get('question', '')
        picked = [row for code, row in self.universe.items() if code in question]
        return json.dumps(_both_scheme_payload(list(reversed(picked))), ensure_ascii=False)


class _StubProvider:
    name = 'wind'

    def __init__(self, universe):
        self.transport = _StubTransport(universe)
        self.map_calls = []

    def scope_of(self, capability):
        return 'public_market'

    def build_transport(self, post):
        return self.transport

    def tool_for(self, capability):
        assert capability == wind_stock.CAPABILITY
        return wind_stock.STOCK_BASICINFO_TOOL

    def map_args(self, capability, **kwargs):
        self.map_calls.append((capability, kwargs))
        return kwargs

    def extract(self, text, columns=None):
        payload = json.loads(text)
        node = payload['data']
        if isinstance(node, dict) and 'data' in node:
            node = node['data']
        if isinstance(node, list):
            node = node[0] if node else {'columns': [], 'rows': []}
        names = [c['name'] for c in node.get('columns') or []]
        rows = [dict(zip(names, row)) for row in node.get('rows') or []]
        for row in rows:
            for col in columns or ():
                row.setdefault(col, None)
        return rows


def _payload(columns, rows):
    """复刻实测形状：多包一层 ``data.data[]``。"""
    return {
        'data': {'data': [{'columns': [{'name': c, 'type': 'string'} for c in columns], 'rows': rows}]},
        'error': None,
    }


def _both_scheme_payload(rows):
    return _payload(
        ['Wind代码', '证券简称', '申万一级行业', '申万一级行业.行业级别', '证监会门类行业', '证监会门类行业.行业级别'],
        rows,
    )


# ── 代码归一 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    'raw,expected',
    [
        ('600519', '600519.SH'),
        ('688981', '688981.SH'),
        ('000001', '000001.SZ'),
        ('300750', '300750.SZ'),
        ('430047', '430047.BJ'),
        ('110059', '110059.SH'),  # 沪市转债
        ('113050', '113050.SH'),
        ('123108', '123108.SZ'),  # 深市转债
        ('127045', '127045.SZ'),
        ('600519.sh', '600519.SH'),  # 已带后缀：归一不重复加
        ('', None),
        ('60051', None),  # 位数不对
        ('ABCDEF', None),
        ('900901', None),  # B 股不在覆盖范围：宁可留缺口，不错配交易所
    ],
)
def test_to_wind_code(raw, expected):
    assert wind_stock.to_wind_code(raw) == expected


@pytest.mark.parametrize(
    'raw,expected',
    [
        ('110059', True),
        ('123108', True),
        ('132007', True),  # 可交换债，与转债同处理
        ('600519', False),
        ('000001', False),
        ('', False),
    ],
)
def test_is_bond_code(raw, expected):
    assert wind_stock.is_bond_code(raw) == expected


# ── 股票批量 ─────────────────────────────────────────────────────────────


def test_batch_maps_rows_back_by_code_not_order():
    """上游返回顺序与请求顺序不同（实测），必须按 Wind代码 回填。"""
    provider = _StubProvider(
        {
            '002415.SZ': ['002415.SZ', '海康威视', '计算机', '一级行业', '制造业', '门类行业'],
            '600519.SH': ['600519.SH', '贵州茅台', '食品饮料', '一级行业', '制造业', '门类行业'],
        }
    )

    got = wind_stock.fetch_stock_industries(['600519', '002415'], provider=provider, transport=provider.transport)

    assert got['600519']['sw1'] == '食品饮料'
    assert got['600519']['csrc'] == '制造业'
    assert got['600519']['name'] == '贵州茅台'
    assert got['002415']['sw1'] == '计算机'
    # 问句只问两套口径，且代码带交易所后缀
    assert '600519.SH' in provider.map_calls[0][1]['question']


def test_batch_skips_bonds_and_unknown_codes():
    """债券与认不出交易所的代码不进股票批（债券要逐只问，理由见模块 docstring）。"""
    provider = _StubProvider({'600519.SH': ['600519.SH', '贵州茅台', '食品饮料', '一级行业', '制造业', '门类行业']})

    got = wind_stock.fetch_stock_industries(
        ['600519', '110059', '900901'], provider=provider, transport=provider.transport
    )

    assert set(got) == {'600519'}
    question = provider.map_calls[0][1]['question']
    assert '110059' not in question


def test_batch_chunks_by_ten():
    universe = {
        f'{600000 + i}.SH': [f'{600000 + i}.SH', f'股票{i}', '银行', '一级行业', '金融业', '门类行业']
        for i in range(11)
    }
    provider = _StubProvider(universe)
    codes = [f'{600000 + i}' for i in range(11)]

    got = wind_stock.fetch_stock_industries(codes, provider=provider, transport=provider.transport)

    assert len(provider.transport.calls) == 2  # 10 + 1
    assert len(got) == 11


def test_batch_ignores_rows_not_requested():
    """上游可能多回别的代码：认不出的丢掉，不按行序强配。"""
    provider = _StubProvider(
        {
            '600519.SH': ['600519.SH', '贵州茅台', '食品饮料', '一级行业', '制造业', '门类行业'],
            '000002.SZ': ['000002.SZ', '万科A', '房地产', '一级行业', '房地产业', '门类行业'],
        }
    )

    got = wind_stock.fetch_stock_industries(['600519'], provider=provider, transport=provider.transport)

    assert set(got) == {'600519'}


def test_batch_failure_in_one_chunk_keeps_the_others():
    """第一块抛错只丢那 10 只，第二块照常拿到——一次抖动不该废掉整轮。"""
    calls = {'n': 0}

    class _FlakyTransport(_StubTransport):
        def call_tool(self, tool, arguments, token=None):
            calls['n'] += 1
            if calls['n'] == 1:
                raise RuntimeError('boom')
            return super().call_tool(tool, arguments, token=token)

    universe = {
        f'{600000 + i}.SH': [f'{600000 + i}.SH', f'股票{i}', '银行', '一级行业', '金融业', '门类行业']
        for i in range(11)
    }
    provider = _StubProvider(universe)
    transport = _FlakyTransport(universe)

    got = wind_stock.fetch_stock_industries(
        [f'{600000 + i}' for i in range(11)], provider=provider, transport=transport
    )

    assert len(got) == 1  # 第二块的 1 只仍然拿到（第一块抛错只丢那一块）


# ── 可转债 ───────────────────────────────────────────────────────────────


class _UnderlyingTransport(_StubTransport):
    """转债替身：无论问哪只债，都回「正股」那一行（实测行为）。"""

    def call_tool(self, tool, arguments, token=None):
        self.calls.append({'tool': tool, 'arguments': arguments, 'token': token})
        rows = [row for row in self.universe.values()]
        return json.dumps(_both_scheme_payload(rows), ensure_ascii=False)


def test_bond_returns_underlying_industry():
    """传债券代码，上游返回**正股**的行——按行取，不校验返回代码与请求相同。"""
    provider = _StubProvider({'600000.SH': ['600000.SH', '浦发银行', '银行', '一级行业', '金融业', '门类行业']})
    transport = _UnderlyingTransport(provider.transport.universe)

    got = wind_stock.fetch_bond_industry('110059', provider=provider, transport=transport)

    assert got == {'sw1': '银行', 'csrc': '金融业', 'name': '浦发银行', 'underlying': '600000.SH'}
    assert '110059.SH' in provider.map_calls[0][1]['question']


def test_bond_rejects_non_bond_code():
    assert wind_stock.fetch_bond_industry('600519', provider=_StubProvider({})) is None


def test_bond_returns_none_when_upstream_gives_nothing():
    provider = _StubProvider({})
    assert wind_stock.fetch_bond_industry('110059', provider=provider, transport=provider.transport) is None


# ── 可用性判据 ───────────────────────────────────────────────────────────


def test_is_available_requires_both_token_and_url(monkeypatch):
    monkeypatch.setattr(wind_stock, 'is_configured', lambda provider: True)
    monkeypatch.setenv('WIND_STOCK_MCP_URL', 'https://example.invalid/mcp')
    assert wind_stock.is_available() is True

    monkeypatch.delenv('WIND_STOCK_MCP_URL', raising=False)
    assert wind_stock.is_available() is False

    monkeypatch.setattr(wind_stock, 'is_configured', lambda provider: False)
    monkeypatch.setenv('WIND_STOCK_MCP_URL', 'https://example.invalid/mcp')
    assert wind_stock.is_available() is False

# -*- coding: utf-8 -*-
"""基金持仓 / 档案适配器（Wind 基金域，S6）：报告期解析、单位换算、口径区分。

全部替身，不联网。报文形状取自 2026-10-30 真机返回（见
:mod:`app.services.adapters.wind_fund` 模块 docstring 的采样记录）。
"""

import json

import pytest

from app.services.adapters import wind_fund


def _table(columns, rows):
    return {'columns': [{'name': c, 'type': 'string'} for c in columns], 'rows': rows}


def _payload(*tables):
    return {'data': {'data': list(tables)}, 'error': None}


class _StubTransport:
    """按问句分流：含「资产类别」回资产类别表，否则回持仓表。"""

    def __init__(self, holdings, alloc=None):
        self.holdings = holdings
        self.alloc = alloc
        self.calls = []

    def call_tool(self, tool, arguments, token=None):
        self.calls.append({'tool': tool, 'arguments': arguments, 'token': token})
        question = arguments.get('question', '')
        if '资产类别' in question:
            return json.dumps(self.alloc if self.alloc is not None else _payload(), ensure_ascii=False)
        return json.dumps(self.holdings, ensure_ascii=False)


class _StubProvider:
    name = 'wind_fund'

    def __init__(self, holdings, alloc=None):
        self.transport = _StubTransport(holdings, alloc)

    def scope_of(self, capability):
        return 'public_market'

    def build_transport(self, post):
        return self.transport

    def tool_for(self, capability):
        return {'fund_holdings': 'get_fund_holdings', 'fund_info': 'get_fund_info'}[capability]

    def map_args(self, capability, **kwargs):
        return kwargs

    def extract(self, text, columns=None):
        payload = json.loads(text)
        out = []
        for node in payload['data']['data']:
            names = [c['name'] for c in node.get('columns') or []]
            out.extend(dict(zip(names, row)) for row in node.get('rows') or [])
        return out


#: 实测列名（2026-10-30 真机，注意「重仓股**持有**市值」这个变体）
_HOLDING_COLUMNS = [
    'Wind代码',
    '证券简称',
    '2025年中报重仓股票代码',
    '2025年中报重仓股票名称',
    '2025年中报重仓股持股数量',
    '2025年中报重仓股持有市值',
    '2025年中报重仓股市值占基金资产净值比',
    '名次',
]
_HOLDING_ROWS = [['510300.SH', '华泰柏瑞沪深300ETF', '600519.SH', '贵州茅台', 11194143, 157.7837, 4.2109, 1]]

_ALLOC = _payload(
    _table(
        [
            'Wind代码',
            '证券简称',
            '2025年中报股票市值占基金资产净值比',
            '2025年中报其他资产占基金资产净值比',
            '2025年中报债券市值占基金资产净值比',
            '2025年中报银行存款占基金资产净值比',
        ],
        [['510300.SH', '华泰柏瑞沪深300ETF', 98.8876, 0.1082, None, 1.0804]],
    )
)


def _run(holdings=None, alloc=None, code='510300.SH', period='2025年中报'):
    provider = _StubProvider(holdings or _payload(_table(_HOLDING_COLUMNS, _HOLDING_ROWS)), alloc)
    return wind_fund.fetch_fund_holdings(code, period, provider=provider, transport=provider.transport), provider


# ── 报告期 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('column', 'expected'),
    [
        ('2025年中报前十大重仓股股票代码', '2025Q2'),
        ('2024年年报前十大重仓股股票代码', '2024Q4'),
        ('2025年一季报前十大重仓股股票代码', '2025Q1'),
        ('2025年三季报前十大重仓股股票代码', '2025Q3'),
        ('最新重仓股股票代码', None),
    ],
)
def test_parse_report_period(column, expected):
    """``中报`` 是 Q2、``年报`` 是 Q4；读不出（如「最新」）返回 ``None`` 而不是猜。"""
    assert wind_fund.parse_report_period([column]) == expected


def test_unknown_period_is_none_not_guessed():
    """上游不给期次时返回 ``None`` —— 不能默认成今天所在季度（那是假数据）。"""
    result, _ = _run(holdings=_payload(_table(['Wind代码', '最新重仓股股票代码'], [['510300.SH', '600519.SH']])))
    assert result['report_period'] is None


# ── 口径与单位 ────────────────────────────────────────────────────────


def test_question_asks_for_stock_code():
    """必须问「股票代码」。

    不问代码时上游只给名称（``FundHolding.stock_code`` 非空，写不进去），
    且比例列会退化成资产类别口径（98.8876 出现在每一行）。
    """
    _, provider = _run()
    question = provider.transport.calls[0]['arguments']['question']
    assert '股票代码' in question


def test_units_are_converted_to_holding_table_conventions():
    """上游「股」「亿元」→ ``FundHolding`` 的「万股」「万元」。"""
    result, _ = _run()
    row = result['rows'][0]
    assert row['shares'] == pytest.approx(1119.4143), '股 → 万股（÷1e4）'
    assert row['market_value'] == pytest.approx(1577837.0), '亿元 → 万元（×1e4）'
    assert row['stock_code'] == '600519', '交易所后缀必须去掉（表口径是裸代码）'
    assert row['rank'] == 1


def test_ratio_is_per_stock_not_asset_class():
    """比例必须是个股口径（4.2109），不是资产类别口径（98.8876）。"""
    result, _ = _run()
    assert result['rows'][0]['ratio'] == pytest.approx(4.2109)


def test_hk_code_suffix_is_stripped():
    """港股 ``0700.HK`` → ``0700``（表口径：港股 5 位、不补零）。"""
    holdings = _payload(
        _table(
            ['Wind代码', '证券简称', '2025年中报重仓股票代码', '2025年中报重仓股票名称', '名次'],
            [['005827.OF', '易方达蓝筹精选', '0700.HK', '腾讯控股', 1]],
        )
    )
    result, _ = _run(holdings=holdings, code='005827.OF')
    assert result['rows'][0]['stock_code'] == '0700'


def test_market_value_column_name_variant_is_tolerated():
    """「持股市值」与「持有市值」是同一列 —— 实测同一天两次调用列名不同。"""
    variant = [c.replace('持有市值', '持股市值') for c in _HOLDING_COLUMNS]
    result, _ = _run(holdings=_payload(_table(variant, _HOLDING_ROWS)))
    assert result['rows'][0]['market_value'] == pytest.approx(1577837.0)


def test_row_without_stock_code_is_skipped_with_warning():
    """缺代码的行不能写库（``stock_code`` 非空），但必须留痕而不是静默丢。"""
    holdings = _payload(
        _table(
            ['Wind代码', '证券简称', '2025年中报重仓股票名称', '名次'],
            [['510300.SH', '华泰柏瑞沪深300ETF', '贵州茅台', 1]],
        )
    )
    result, _ = _run(holdings=holdings)
    assert result['rows'] == []
    assert result['warnings'], '被跳过的行必须在 warnings 里出现'


# ── 资产类别配置 ──────────────────────────────────────────────────────


def test_asset_alloc_is_a_separate_call_and_skips_none():
    """资产类别单问一次；取不到的类别**不补 0**（``None`` 与「真的 0%」必须可区分）。"""
    result, provider = _run(alloc=_ALLOC)
    alloc = result['alloc']
    assert alloc['stock'] == pytest.approx(98.8876)
    assert alloc['cash'] == pytest.approx(1.0804)
    assert 'bond' not in alloc, '上游给 null 的类别不该出现（不能当成 0%）'
    assert len(provider.transport.calls) == 2, '持仓一问 + 资产类别一问'


def test_asset_alloc_failure_does_not_break_holdings():
    """资产类别取数失败只降级，不拖垮持仓明细。"""

    class _FlakyAlloc(_StubTransport):
        def call_tool(self, tool, arguments, token=None):
            if '资产类别' in arguments.get('question', ''):
                raise RuntimeError('boom')
            return super().call_tool(tool, arguments, token)

    provider = _StubProvider(_payload(_table(_HOLDING_COLUMNS, _HOLDING_ROWS)))
    provider.transport = _FlakyAlloc(provider.transport.holdings)
    result = wind_fund.fetch_fund_holdings('510300.SH', '2025年中报', provider=provider, transport=provider.transport)
    assert len(result['rows']) == 1
    assert result['alloc'] == {}


def test_empty_holdings_returns_empty_rows():
    result, _ = _run(holdings=_payload())
    assert result['rows'] == []
    assert result['fund_code'] == '510300.SH'


# ── 档案 ──────────────────────────────────────────────────────────────


def test_fetch_fund_profile_maps_fields():
    payload = _payload(
        _table(
            ['Wind代码', '证券简称', '投资类型_二级分类', '跟踪指数名称', '管理费率', '托管费率', '现任基金经理姓名'],
            [['510300.SH', '华泰柏瑞沪深300ETF', '被动指数型基金', '沪深300', 0.15, 0.05, '柳军']],
        )
    )
    provider = _StubProvider(payload)
    profile = wind_fund.fetch_fund_profile('510300.SH', provider=provider, transport=provider.transport)
    assert profile == {
        'fund_code': '510300.SH',
        'name': '华泰柏瑞沪深300ETF',
        'category': '被动指数型基金',
        'tracking_index': '沪深300',
        'management_fee': pytest.approx(0.15),
        'custody_fee': pytest.approx(0.05),
        'manager': '柳军',
    }


def test_is_available_requires_only_token(monkeypatch):
    monkeypatch.setattr(wind_fund, 'is_configured', lambda provider: True)
    monkeypatch.delenv('WIND_FUND_MCP_URL', raising=False)
    assert wind_fund.is_available() is True
    monkeypatch.setattr(wind_fund, 'is_configured', lambda provider: False)
    assert wind_fund.is_available() is False

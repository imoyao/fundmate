# -*- coding: utf-8 -*-
"""万得指数日线适配器（S4 / #2476）：解析、去重、窗口、可用性判据。

全部替身，不联网、不读真实凭据。真机验证见 `#2516` / `#2476` 的采样评论
（`885002.WI` 全历史 5537 条，2003-12-31 起，2026-10-22 收 7206.3199）。
"""

import json
from datetime import date, timedelta

import pytest

from app.services.adapters import wind_index


class _StubTransport:
    def __init__(self, payload):
        self.calls = []
        self._text = json.dumps(payload, ensure_ascii=False)

    def call_tool(self, tool, arguments, token=None):
        self.calls.append({'tool': tool, 'arguments': arguments, 'token': token})
        return self._text


class _StubProvider:
    name = 'wind'

    def __init__(self, payload):
        self.transport = _StubTransport(payload)
        self.map_kwargs = None

    def scope_of(self, capability):
        return 'public_market'

    def build_transport(self, post):
        return self.transport

    def tool_for(self, capability):
        return 'market_call_tool'

    def map_args(self, capability, **kwargs):
        self.map_kwargs = (capability, kwargs)
        return {'toolName': 'get_index_kline', 'arguments': json.dumps(kwargs, ensure_ascii=False)}

    def extract(self, text, columns=None):
        payload = json.loads(text)
        names = [c['name'] for c in payload['data']['columns']]
        return [dict(zip(names, row)) for row in payload['data']['rows']]


def _payload(rows):
    return {
        'data': {
            'columns': [{'name': 'TIME', 'type': 'string'}, {'name': 'MATCH', 'type': 'string'}],
            'rows': rows,
        },
        'error': None,
    }


@pytest.mark.parametrize(
    'raw,expected',
    [
        ('2026-10-22T00:00:00.000+08:00', date(2026, 10, 22)),
        ('2026-10-22', date(2026, 10, 22)),
        ('', None),
        (None, None),
        ('not-a-date', None),
    ],
)
def test_parse_trade_date(raw, expected):
    assert wind_index._parse_trade_date(raw) == expected


@pytest.mark.parametrize('raw,expected', [('7206.3199', 7206.3199), ('', None), (None, None), ('--', None)])
def test_parse_close_never_writes_zero_for_missing(raw, expected):
    """缺失返回 ``None`` 而不是 ``0``：写 0 会被下游算成一个 -100% 的交易日。"""
    assert wind_index._parse_close(raw) == expected


def test_fetch_sorts_and_dedupes_same_day(monkeypatch):
    payload = _payload(
        [
            ['2026-10-22T00:00:00.000+08:00', '7206.3199'],
            ['2026-10-21T00:00:00.000+08:00', '7201.5089'],
            ['2026-10-21T00:00:00.000+08:00', '7201.6000'],  # 上游偶发重复行：以最后一条为准
            ['2026-10-20T00:00:00.000+08:00', ''],  # 空收盘：跳过而非写 0
        ]
    )
    provider = _StubProvider(payload)
    monkeypatch.setattr(wind_index, 'get_provider', lambda name: provider)
    monkeypatch.setattr(wind_index, 'resolve_token', lambda provider, scope: 'k')

    rows = wind_index.fetch_index_daily('885002.WI', full_sync=False)

    assert [r['trade_date'] for r in rows] == [date(2026, 10, 21), date(2026, 10, 22)]
    assert rows[0]['close'] == pytest.approx(7201.6)
    assert provider.transport.calls[0]['arguments']['toolName'] == 'get_index_kline'
    assert provider.transport.calls[0]['token'] == 'k'


def test_fetch_passes_wind_code_as_is_and_requires_date_window(monkeypatch):
    """`windcode` 认代码（不做名称映射）；`begin_date` / `end_date` 必填且随全量/增量变。"""
    provider = _StubProvider(_payload([]))
    monkeypatch.setattr(wind_index, 'get_provider', lambda name: provider)
    monkeypatch.setattr(wind_index, 'resolve_token', lambda provider, scope: 'k')

    wind_index.fetch_index_daily('885002.WI', full_sync=True)
    capability, kwargs = provider.map_kwargs

    assert capability == 'index_kline'
    assert kwargs['windcode'] == '885002.WI', '万得 K 线认代码，多做名称映射会把能取的代码挡在门外'
    assert kwargs['period'] == '10'
    assert kwargs['begin_date'] == wind_index._FULL_SYNC_BEGIN.isoformat()
    assert kwargs['end_date'] == date.today().isoformat()

    wind_index.fetch_index_daily('885002.WI', full_sync=False)
    _, kwargs = provider.map_kwargs
    expected_begin = (date.today() - timedelta(days=wind_index._INCREMENT_DAYS)).isoformat()
    assert kwargs['begin_date'] == expected_begin


def test_is_available_requires_both_token_and_url(monkeypatch):
    """只有 Token 没地址（或反之）都不算可用：缺一个的结果是 WindEndpointMissing，
    那会被 job 记成「真故障」，而它其实是「没配」。"""
    monkeypatch.setattr(wind_index, 'is_configured', lambda provider: True)
    monkeypatch.setenv(wind_index.WIND_MCP_URL_ENV, 'https://example.invalid/mcp')
    assert wind_index.is_available() is True

    monkeypatch.delenv(wind_index.WIND_MCP_URL_ENV, raising=False)
    assert wind_index.is_available() is False

    monkeypatch.setattr(wind_index, 'is_configured', lambda provider: False)
    monkeypatch.setenv(wind_index.WIND_MCP_URL_ENV, 'https://example.invalid/mcp')
    assert wind_index.is_available() is False

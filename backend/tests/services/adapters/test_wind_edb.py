# -*- coding: utf-8 -*-
"""万得 EDB 适配器：上游契约（工具名 / 参数名）、metrics 解析、精确名过滤。

全部替身，不联网、不读真实凭据。真机证据见 #1502 评论（2026-11-16 复核：
``economic_query_indicator_series`` + ``startDate``/``endDate`` 返回 10 个同族行业、
每行业 251 个日频点，形状 ``metrics[].meta.name`` + ``date[]`` / ``value[]``）。

**本文件存在的理由**：``wind_edb`` 是唯一没有专项测试的 Wind adapter，于是「上游改工具名
+ 参数名」这件事同时躲过了实现与测试 —— 换手率维度静默降级、无告警。第一条用例即钉住
请求参数名，防止 ``beginDate`` 这类上游已废弃的名字回归。
"""

import json
from datetime import date

import pytest

from app.services.adapters import wind_edb


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

    def scope_of(self, capability):
        return 'public_market'

    def tool_for(self, capability):
        return 'economic_query_indicator_series'

    def build_transport(self, post):
        return self.transport


@pytest.fixture
def stub(monkeypatch):
    """把 provider / 凭据 / post 工厂全部换成替身，返回已装的 provider。"""

    def _install(payload):
        provider = _StubProvider(payload)
        monkeypatch.setattr(wind_edb, 'get_provider', lambda name: provider)
        monkeypatch.setattr(wind_edb, 'resolve_token', lambda *a, **k: 'stub-token')
        monkeypatch.setattr(wind_edb, '_post_factory', lambda *a, **k: None)
        return provider

    return _install


def test_sends_upstream_date_param_names(stub):
    """上游要 ``startDate`` / ``endDate``；写成 ``beginDate`` 会被网关拒收。"""
    provider = stub({'metrics': []})

    wind_edb.fetch_edb_series('换手率:申万行业指数:汽车', date(2026, 1, 2), date(2026, 1, 5))

    args = provider.transport.calls[0]['arguments']
    assert args == {
        'question': '换手率:申万行业指数:汽车',
        'startDate': '2026-01-02',
        'endDate': '2026-01-05',
    }
    assert 'beginDate' not in args


def test_keeps_only_exactly_matching_indicator(stub):
    """精确名查询上游仍回同族多条（含中信口径），只收 ``meta.name`` 完全相等的那个。"""
    stub(
        {
            'metrics': [
                {
                    'meta': {'name': '换手率:申万行业指数:汽车'},
                    'date': ['20260102', '20260105'],
                    'value': ['1.5', '2'],
                },
                {'meta': {'name': '换手率:申万行业指数:机械设备'}, 'date': ['20260102'], 'value': ['9.9']},
                {'meta': {'name': '换手率:中信行业指数:汽车'}, 'date': ['20260102'], 'value': ['7.7']},
            ]
        }
    )

    series = wind_edb.fetch_edb_series('换手率:申万行业指数:汽车', date(2026, 1, 1), date(2026, 1, 31))

    assert series == {date(2026, 1, 2): 1.5, date(2026, 1, 5): 2.0}


def test_window_filters_out_of_range_and_skips_bad_values(stub):
    """区间外的点丢弃；空值 / 无法解析的日期跳过（不写 0，0 会被分位读成真值）。"""
    stub(
        {
            'metrics': [
                {
                    'meta': {'name': 'X'},
                    'date': ['20251231', '20260102', '20260103', 'bad'],
                    'value': ['1', '', '2', '3'],
                }
            ]
        }
    )

    series = wind_edb.fetch_edb_series('X', date(2026, 1, 1), date(2026, 1, 31))

    assert series == {date(2026, 1, 3): 2.0}


def test_no_metrics_returns_empty_dict(stub):
    """上游确实没有该窗口数据 —— 空字典是合法结果，不是故障。"""
    stub({'metrics': []})

    assert wind_edb.fetch_edb_series('X', date(2026, 1, 1), date(2026, 1, 31)) == {}


def test_non_json_text_raises_bad_response(stub):
    """形状漂移当场显式报错，不静默吞成空序列。"""
    provider = stub({})
    provider.transport._text = 'not json'

    with pytest.raises(wind_edb.McpBadResponse):
        wind_edb.fetch_edb_series('X', date(2026, 1, 1), date(2026, 1, 31))

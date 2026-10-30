# -*- coding: utf-8 -*-
"""Wind 直连域 provider 基类（S6）：域路由、地址默认值、能力归属。

全部替身，不联网。真机端点清单见 :mod:`app.services.mcp.providers.wind_direct`
的模块 docstring（2026-10-30 逐个 initialize + tools/list 采样）。
"""

import pytest

from app.services.mcp import get_provider, provider_names
from app.services.mcp.credentials import DataScope
from app.services.mcp.providers.wind_direct import WIND_DEFAULT_BASE, wind_base


def test_direct_domains_are_registered():
    """三个直连域都进了注册表（没注册 = 调用点拿不到 = 死代码）。"""
    names = provider_names()
    for expected in ('wind_stock', 'wind_fund', 'wind_index'):
        assert expected in names


@pytest.mark.parametrize(
    ('provider_name', 'expected_url'),
    [
        ('wind_stock', f'{WIND_DEFAULT_BASE}/vserver_stock_data/mcp/'),
        ('wind_fund', f'{WIND_DEFAULT_BASE}/vserver_fund_data/mcp/'),
        ('wind_index', f'{WIND_DEFAULT_BASE}/vserver_index_data/mcp/'),
    ],
)
def test_base_url_defaults_to_verified_layout(monkeypatch, provider_name, expected_url):
    """未配任何 URL 环境变量时，地址仍指向已实测的 ``/vserver_{域}/mcp/``。

    这是「代码写了却一直没被调用」的直接约束：如果每个域都要求一个 URL 变量，
    新接的域默认就是死代码。
    """
    monkeypatch.delenv('WIND_MCP_BASE', raising=False)
    monkeypatch.delenv('WIND_STOCK_MCP_URL', raising=False)
    monkeypatch.delenv('WIND_FUND_MCP_URL', raising=False)
    monkeypatch.delenv('WIND_INDEX_MCP_URL', raising=False)
    assert get_provider(provider_name).base_url() == expected_url


def test_base_env_overrides_default(monkeypatch):
    """``WIND_MCP_BASE`` 是部署级覆盖点（内网代理 / 灰度）。"""
    monkeypatch.setenv('WIND_MCP_BASE', 'https://proxy.example.com/')
    assert wind_base() == 'https://proxy.example.com'
    assert get_provider('wind_fund').base_url() == 'https://proxy.example.com/vserver_fund_data/mcp/'


def test_single_domain_override_wins(monkeypatch):
    """单域覆盖优先于 BASE（本地 mock 用）。"""
    monkeypatch.setenv('WIND_MCP_BASE', 'https://proxy.example.com')
    monkeypatch.setenv('WIND_FUND_MCP_URL', 'http://127.0.0.1:9/mcp')
    assert get_provider('wind_fund').base_url() == 'http://127.0.0.1:9/mcp'


def test_scope_is_public_market_for_registered_capabilities():
    """已登记能力一律公开市场（系统 Token）；未登记落到 USER_PRIVATE 而不是静默公用。

    这条防的是父类 ``scope_of`` 的继承陷阱：父类按**自己的**能力表判断，子类能力
    不在其中会一律变成 ``USER_PRIVATE``，表现为「抛 McpUserTokenMissing」。
    """
    fund = get_provider('wind_fund')
    assert fund.scope_of('fund_holdings') == DataScope.PUBLIC_MARKET
    assert fund.scope_of('fund_info') == DataScope.PUBLIC_MARKET
    assert fund.scope_of('not_a_capability') == DataScope.USER_PRIVATE


def test_unknown_capability_raises_keyerror_naming_the_domain():
    """未登记能力抛 KeyError，且文案点明是哪个域 —— 不要只说「Wind 没有这个能力」。"""
    with pytest.raises(KeyError, match='基金域'):
        get_provider('wind_fund').tool_for('etf_holdings')


def test_wire_uses_standard_jsonrpc_not_gateway():
    """直连域**不能**走 ``market_call_tool``（实测那样会得到「工具不存在」）。"""
    body = get_provider('wind_fund')._wire('get_fund_holdings', {'question': 'q'})
    assert body['method'] == 'tools/call'
    assert body['params'] == {'name': 'get_fund_holdings', 'arguments': {'question': 'q'}}


def test_gateway_provider_keeps_gateway_wire():
    """``wind``（聚合网关）保持原形状：数据工具仍经 ``market_call_tool`` 转发。"""
    body = get_provider('wind')._wire('get_index_kline', {'windcode': '000300.SH'})
    assert body['params']['name'] == 'market_call_tool'
    assert body['params']['arguments']['toolName'] == 'get_index_kline'

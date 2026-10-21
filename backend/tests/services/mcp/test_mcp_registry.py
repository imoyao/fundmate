# -*- coding: utf-8 -*-
"""MCP provider 注册表 / 且慢 provider 元信息（#2488，S1）。

钉住三件事，都是「抽出来之后会不会悄悄漂移」的判据：

1. ``get_provider('qieman')`` 真能取到（注册惰性加载有效），且元信息与常量一致；
2. 未知 provider / 未知能力**抛错而不是返回空**（返回空会在业务层变成「这组合没持仓」）；
3. 空 token 不发假 key（「没配凭据」不得被伪装成「凭据错误」），以及 §8 的地址覆盖点，
   外加 ``adapters.qieman_fetcher`` 的**兼容再导出**仍然指向同一批常量。
"""

import pytest

from app.services.mcp import UnknownMcpProvider, get_provider, provider_names
from app.services.mcp.providers.qieman import (
    QIEMAN_CLIENT_INFO,
    QIEMAN_MCP_URL,
    QIEMAN_PROTOCOL_VERSION,
    QIEMAN_STRATEGY_COMPOSITION_TOOL,
    QIEMAN_STRATEGY_DETAIL_TOOL,
    QIEMAN_TOOL,
)


def test_qieman_provider_is_registered_with_matching_metadata():
    provider = get_provider('qieman')

    assert provider.name == 'qieman'
    assert provider.protocol_version == QIEMAN_PROTOCOL_VERSION
    assert provider.client_info == QIEMAN_CLIENT_INFO
    assert provider.tool_for('latest_quotations') == QIEMAN_TOOL
    assert provider.tool_for('strategy_details') == QIEMAN_STRATEGY_DETAIL_TOOL
    assert provider.tool_for('strategy_composition') == QIEMAN_STRATEGY_COMPOSITION_TOOL
    assert 'qieman' in provider_names()


def test_unknown_provider_raises_with_registered_names():
    with pytest.raises(UnknownMcpProvider, match='已注册'):
        get_provider('wind')


def test_unknown_capability_raises_key_error():
    with pytest.raises(KeyError, match='且慢没有能力'):
        get_provider('qieman').tool_for('no_such_capability')


def test_empty_token_does_not_forge_api_key_header(monkeypatch):
    monkeypatch.delenv('QIEMAN_MCP_URL', raising=False)
    headers = get_provider('qieman').auth_headers('')

    assert 'x-api-key' not in headers
    assert headers['Origin'] == QIEMAN_MCP_URL
    assert headers['Referer'] == QIEMAN_MCP_URL + '/'


def test_base_url_can_be_overridden_for_local_mock(monkeypatch):
    """设计文档 §8 的预留点：环境变量覆盖服务地址（供本地 mock / 一键切换）。"""
    monkeypatch.setenv('QIEMAN_MCP_URL', 'http://127.0.0.1:9/mcp')
    provider = get_provider('qieman')

    assert provider.base_url() == 'http://127.0.0.1:9/mcp'
    assert provider.auth_headers('k')['Origin'] == 'http://127.0.0.1:9/mcp'


def test_fetcher_reexports_provider_constants():
    """``adapters.qieman_fetcher`` 仍导出同样的常量（旧导入点不必改）。"""
    from app.services.adapters import qieman_fetcher

    assert qieman_fetcher.QIEMAN_MCP_URL == QIEMAN_MCP_URL
    assert qieman_fetcher.QIEMAN_PROTOCOL_VERSION == QIEMAN_PROTOCOL_VERSION
    assert qieman_fetcher.QIEMAN_STRATEGY_DETAIL_TOOL == QIEMAN_STRATEGY_DETAIL_TOOL
    assert qieman_fetcher.QIEMAN_STRATEGY_COMPOSITION_TOOL == QIEMAN_STRATEGY_COMPOSITION_TOOL
    assert qieman_fetcher.QIEMAN_TOOL == QIEMAN_TOOL

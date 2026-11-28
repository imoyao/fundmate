# -*- coding: utf-8 -*-
"""连接校验（S5f）回归网。

判定口径：校验 = 用户自己的凭据真的能调通上游并报出工具清单，不是表里有行凭据。
覆盖四条：
- 握手 + tools/list 全链路走真 ``McpTransport``（只把 HTTP 打桩）——桩只认协议形状，
  与真实报文同构（initialize → notifications/initialized → tools/list）；
- 没连过 ⇒ ``McpUserTokenMissing``（响亮失败，不回退系统 Token）；
- 上游拒绝（401）⇒ 类型化 ``McpError``，文案可直接展示；
- tzzb provider 的鉴权形状：Bearer 头、空 token 不伪造占位值、工具名未采样时拒绝直调。
"""

import json
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from app.services.mcp import connection_check
from app.services.mcp.connection_check import check_connection
from app.services.mcp.errors import McpError, McpUserTokenMissing
from app.services.mcp.providers.tzzb import TzzbProvider
from app.services.mcp.user_credentials import save_oauth_token, save_static_token


@pytest.fixture(autouse=True)
def credential_key(monkeypatch):
    monkeypatch.setenv('MCP_CREDENTIAL_KEY', Fernet.generate_key().decode('ascii'))
    monkeypatch.setenv('MCP_CREDENTIAL_KEY_VERSION', '1')


_TOOLS = [
    {'name': 'list_accounts', 'description': '发现上游账户'},
    {'name': 'get_positions', 'description': '查询持仓'},
    {'description': '缺 name 的畸形条目应被丢弃'},
]


def _fake_response(payload, status=200, sse=False):
    if sse:
        text = 'event: message\ndata: ' + json.dumps(payload) + '\n\n'
        return SimpleNamespace(
            status_code=status, headers={'content-type': 'text/event-stream'}, text=text, json=lambda: payload
        )
    return SimpleNamespace(
        status_code=status,
        headers={'content-type': 'application/json'},
        text=json.dumps(payload),
        json=lambda: payload,
    )


@pytest.fixture
def fake_upstream_tools(monkeypatch):
    """把传输层的 HTTP 打成桩：只认 MCP 协议形状（不 import requests、不出网）。"""
    calls = []

    def fake_post_factory(provider, token, route=None):
        def post(payload, sid):
            calls.append({'payload': payload, 'sid': sid, 'token': token, 'route': route})
            method = payload.get('method')
            if method == 'initialize':
                return SimpleNamespace(status_code=200, headers={}, text='{}', json=lambda: {'result': {}})
            if method == 'notifications/initialized':
                return SimpleNamespace(status_code=200, headers={}, text='', json=lambda: {})
            if method == 'tools/list':
                return _fake_response({'result': {'tools': _TOOLS}})
            raise AssertionError(f'意外的 MCP 方法：{method}')

        return post

    monkeypatch.setattr(connection_check, '_post_factory', fake_post_factory)
    return calls


@pytest.fixture
def qieman_key(db):
    save_static_token(1, 'qieman', 'user-key-1')


def test_check_returns_normalized_tools(fake_upstream_tools, qieman_key):
    result = check_connection('qieman', 1)

    assert result['provider'] == 'qieman'
    assert result['tool_count'] == 2
    assert [tool['name'] for tool in result['tools']] == ['list_accounts', 'get_positions']
    # 链路必须真的握手 + 拉清单（不是读缓存编数据）
    methods = [call['payload'].get('method') for call in fake_upstream_tools]
    assert methods == ['initialize', 'notifications/initialized', 'tools/list']


def test_check_requires_user_credential(fake_upstream_tools):
    with pytest.raises(McpUserTokenMissing):
        check_connection('qieman', 42)


def test_check_upstream_reject_is_typed(fake_upstream_tools, qieman_key, monkeypatch):
    def broken_factory(provider, token, route=None):
        def post(payload, sid):
            return _fake_response({'error': 'denied'}, status=401)

        return post

    monkeypatch.setattr(connection_check, '_post_factory', broken_factory)
    with pytest.raises(McpError) as excinfo:
        check_connection('qieman', 1)
    assert excinfo.value.user_message


def test_check_parses_sse_frame(fake_upstream_tools, qieman_key, monkeypatch):
    def sse_factory(provider, token, route=None):
        def post(payload, sid):
            if payload.get('method') == 'tools/list':
                return _fake_response({'result': {'tools': _TOOLS}}, sse=True)
            if payload.get('method') == 'initialize':
                return SimpleNamespace(status_code=200, headers={}, text='{}', json=lambda: {'result': {}})
            return SimpleNamespace(status_code=200, headers={}, text='', json=lambda: {})

        return post

    monkeypatch.setattr(connection_check, '_post_factory', sse_factory)
    result = check_connection('qieman', 1)
    assert result['tool_count'] == 2


def test_tzzb_auth_headers_bearer_shape():
    provider = TzzbProvider()
    assert provider.auth_headers('tok-1') == {'Authorization': 'Bearer tok-1'}
    # 空 token 不伪造占位值（基类红线）
    assert provider.auth_headers('') == {}


def test_tzzb_tool_for_refuses_unsampled_tools():
    provider = TzzbProvider()
    with pytest.raises(KeyError):
        provider.tool_for('list_accounts')


def test_qieman_oauth_credential_routes_to_partner_gateway(fake_upstream_tools, db):
    """OAuth 凭据的 verify 必须打 partner 网关 + Bearer，不能拿去平台端点（#3304）。"""
    save_oauth_token(
        1, 'qieman', access_token='oauth-token-1', token_endpoint='https://stargate-partner.yingmi.com/oauth/token'
    )

    check_connection('qieman', 1)

    # 桩收到 route = (partner 端点, Bearer 头)；Origin/Referer 齐全（WAF 判来源）
    route = fake_upstream_tools[0]['route']
    assert route is not None
    url, headers = route
    assert url == 'https://stargate-partner.yingmi.com/mcp/v2/oauth/qieman'
    assert headers['Authorization'] == 'Bearer oauth-token-1'
    assert headers['Origin'] == url
    assert headers['Referer'] == url + '/'

    # 同一 token 不能再带 x-api-key 形状（两种凭据语义不同，混用即假连接）
    assert 'x-api-key' not in headers


def test_qieman_static_credential_keeps_platform_endpoint(fake_upstream_tools, qieman_key):
    """static_token 凭据走 provider 默认端点（route=None），平台数据面行为不变。"""
    check_connection('qieman', 1)
    assert fake_upstream_tools[0]['route'] is None


def test_tzzb_oauth_credential_falls_back_to_default_endpoint(fake_upstream_tools, db):
    """未登记路由的 OAuth provider（tzzb）回落默认端点——其 OAuth 与数据面同主机。"""
    save_oauth_token(1, 'tzzb', access_token='tzzb-token-1', token_endpoint='https://tzzb.10jqka.com.cn/oauth2/token')

    check_connection('tzzb', 1)

    assert fake_upstream_tools[0]['route'] is None
    assert fake_upstream_tools[0]['token'] == 'tzzb-token-1'

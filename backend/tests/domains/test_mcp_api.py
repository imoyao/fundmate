# -*- coding: utf-8 -*-
"""MCP 连接管理 API 回归（S5c）。

重点不是"接口能返回 200"，而是：

- 所有读写都按 ``g.current_user`` 隔离，请求里传 user_id 也不生效；
- 回调免登录但 state 一次性，重放必须 400；
- 未登记的 provider 不接受写库。
"""

import json
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet

from app.core.auth import _is_public
from app.domains.users.models import User
from app.services.mcp import oauth
from app.services.mcp.user_credentials import load_credential, save_static_token


@pytest.fixture(autouse=True)
def credential_key(monkeypatch):
    monkeypatch.setenv('MCP_CREDENTIAL_KEY', Fernet.generate_key().decode('ascii'))
    monkeypatch.setenv('MCP_CREDENTIAL_KEY_VERSION', '1')
    monkeypatch.delenv('MCP_TZZB_CLIENT_ID', raising=False)
    monkeypatch.setenv('MCP_OAUTH_REDIRECT_URI', 'http://127.0.0.1:5000/api/mcp/oauth/callback/')
    yield


@pytest.fixture
def fake_upstream(monkeypatch):
    def fake_post(url, data, as_json=False):
        if url.endswith('/register'):
            return {'client_id': 'api-client-1'}
        if url.endswith('/token'):
            return {'access_token': 'api-access', 'expires_in': 3600}
        if url.endswith('/revoke'):
            return {}
        raise AssertionError(url)

    monkeypatch.setattr(oauth, '_http_post', fake_post)


def test_callback_path_is_public_but_connections_are_not():
    assert _is_public('/api/mcp/oauth/callback/', 'GET') is True
    assert _is_public('/api/mcp/connections/', 'GET') is False
    assert _is_public('/api/mcp/oauth/begin/', 'POST') is False


def test_list_connections_is_scoped_to_current_user(client, db):
    other = User(username='mcp-other', family_id=1)
    db.add(other)
    db.flush()
    db.commit()
    save_static_token(other.id, 'qieman', 'other-user-key')

    resp = client.get('/api/mcp/connections/')
    assert resp.status_code == 200
    assert resp.get_json()['data'] == []

    # 请求里传 user_id 也不能改变归属（视图只认 g.current_user）
    resp = client.post(
        '/api/mcp/connections/static/', json={'provider': 'qieman', 'api_key': 'my-key', 'user_id': other.id}
    )
    assert resp.status_code == 200
    listing = client.get('/api/mcp/connections/').get_json()['data']
    assert [row['provider'] for row in listing] == ['qieman']
    assert load_credential(other.id, 'qieman').token == 'other-user-key'


def test_static_connect_rejects_unregistered_provider(client):
    resp = client.post('/api/mcp/connections/static/', json={'provider': 'evil.example.com', 'api_key': 'x'})
    assert resp.status_code == 422


def test_disconnect_deletes_credential(client):
    client.post('/api/mcp/connections/static/', json={'provider': 'qieman', 'api_key': 'to-delete'})
    assert client.get('/api/mcp/connections/').get_json()['data']

    resp = client.delete('/api/mcp/connections/qieman/')
    assert resp.status_code == 200
    assert client.get('/api/mcp/connections/').get_json()['data'] == []


def test_oauth_begin_callback_and_replay(client, fake_upstream):
    begin_resp = client.post('/api/mcp/oauth/begin/', json={'provider': 'tzzb'})
    assert begin_resp.status_code == 200
    data = begin_resp.get_json()['data']
    params = parse_qs(urlparse(data['authorization_url']).query)
    state = params['state'][0]
    assert params['code_challenge_method'] == ['S256']

    callback_resp = client.get(f'/api/mcp/oauth/callback/?state={state}&code=auth-code')
    assert callback_resp.status_code == 302
    assert 'mcp_connected=1' in callback_resp.headers['Location']

    listing = client.get('/api/mcp/connections/').get_json()['data']
    assert [row['provider'] for row in listing] == ['tzzb']

    # 重放：state 已消费，必须 400 而不是再次写库
    replay = client.get(f'/api/mcp/oauth/callback/?state={state}&code=auth-code')
    assert replay.status_code == 400


def test_oauth_callback_redirect_uses_hash_route(client, fake_upstream):
    """回跳必须落 hash 路由：本项目 VITE_ROUTER_HISTORY=hash。

    普通路径 ``/settings/mcp-connections?...`` 会让 SPA 加载后 hash 为空 →
    路由守卫重定向到登录页，用户授权成功却看不到结果。query 必须在 hash 段内，
    Vue Router 的 ``useRoute().query`` 才读得到（页面据此弹一次性成功提示）。
    """
    begin_resp = client.post('/api/mcp/oauth/begin/', json={'provider': 'tzzb'})
    state = parse_qs(urlparse(begin_resp.get_json()['data']['authorization_url']).query)['state'][0]
    callback_resp = client.get(f'/api/mcp/oauth/callback/?state={state}&code=auth-code')
    assert callback_resp.status_code == 302

    location = callback_resp.headers['Location']
    path, separator, raw_query = urlparse(location).fragment.partition('?')
    assert path == '/settings/mcp-connections', location
    assert separator == '?', location
    assert parse_qs(raw_query) == {
        'mcp_connected': ['1'],
        'provider': ['tzzb'],
    }


def test_oauth_callback_redirect_honors_env_override(client, fake_upstream, monkeypatch):
    """history 模式部署可用 env 覆盖默认 hash 路径，但仍拒绝外链。"""
    monkeypatch.setenv('MCP_OAUTH_SUCCESS_REDIRECT', '/custom/landing')
    begin_resp = client.post('/api/mcp/oauth/begin/', json={'provider': 'tzzb'})
    state = parse_qs(urlparse(begin_resp.get_json()['data']['authorization_url']).query)['state'][0]
    resp = client.get(f'/api/mcp/oauth/callback/?state={state}&code=auth-code')
    assert resp.headers['Location'].startswith('/custom/landing?')

    monkeypatch.setenv('MCP_OAUTH_SUCCESS_REDIRECT', 'https://evil.example/')
    begin_resp = client.post('/api/mcp/oauth/begin/', json={'provider': 'tzzb'})
    state = parse_qs(urlparse(begin_resp.get_json()['data']['authorization_url']).query)['state'][0]
    resp = client.get(f'/api/mcp/oauth/callback/?state={state}&code=auth-code')
    assert resp.headers['Location'].startswith('/#/settings/mcp-connections?')


def test_oauth_begin_rejects_non_oauth_provider(client):
    resp = client.post('/api/mcp/oauth/begin/', json={'provider': 'qieman'})
    assert resp.status_code == 422


def _stub_upstream_tools(monkeypatch):
    """把连接校验的 HTTP 细节打桩：只认 MCP 协议形状，不出网。"""
    from types import SimpleNamespace

    from app.services.mcp import connection_check

    def factory(provider, token):
        def post(payload, sid):
            method = payload.get('method')
            if method == 'tools/list':
                body = json.dumps({'result': {'tools': [{'name': 'list_accounts', 'description': '发现上游账户'}]}})
                payload = json.loads(body)
                return SimpleNamespace(
                    status_code=200, headers={'content-type': 'application/json'}, text=body, json=lambda: payload
                )
            if method == 'initialize':
                return SimpleNamespace(status_code=200, headers={}, text='{}', json=lambda: {'result': {}})
            return SimpleNamespace(status_code=200, headers={}, text='', json=lambda: {})

        return post

    monkeypatch.setattr(connection_check, '_post_factory', factory)


def test_verify_requires_connection(client, monkeypatch):
    """没连过的服务校验必须 422，文案直接可读（不是 500 或空响应）。"""
    _stub_upstream_tools(monkeypatch)
    resp = client.post('/api/mcp/connections/tzzb/verify/')
    assert resp.status_code == 422
    message = resp.get_json()['message']
    assert 'Token' in message  # 文案直接可读：指出需要用户本人的 Token
    assert 'tzzb' in message


def test_verify_returns_upstream_tools(client, db, monkeypatch):
    """连接后校验返回上游工具清单 —— 「连接之后能干什么」的直接回答。"""
    _stub_upstream_tools(monkeypatch)
    save_static_token(1, 'qieman', 'user-key-1')
    resp = client.post('/api/mcp/connections/qieman/verify/')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['tool_count'] == 1
    assert data['tools'][0]['name'] == 'list_accounts'
    assert 'description' in data['tools'][0]


def test_verify_rejects_unknown_provider(client):
    assert client.post('/api/mcp/connections/nope/verify/').status_code == 422

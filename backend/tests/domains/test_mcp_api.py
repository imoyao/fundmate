# -*- coding: utf-8 -*-
"""MCP 连接管理 API 回归（S5c）。

重点不是"接口能返回 200"，而是：

- 所有读写都按 ``g.current_user`` 隔离，请求里传 user_id 也不生效；
- 回调免登录但 state 一次性，重放必须 400；
- 未登记的 provider 不接受写库。
"""

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
    oauth._CLIENT_IDS.clear()
    yield
    oauth._CLIENT_IDS.clear()


@pytest.fixture
def fake_upstream(monkeypatch):
    def fake_post(url, data):
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


def test_oauth_begin_rejects_non_oauth_provider(client):
    resp = client.post('/api/mcp/oauth/begin/', json={'provider': 'qieman'})
    assert resp.status_code == 422

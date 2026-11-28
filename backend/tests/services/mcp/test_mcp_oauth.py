# -*- coding: utf-8 -*-
"""浏览器授权编排回归（S5b）。

红线用例：

- state 一次性：第二次回调必须拒绝（否则授权码可被重放）；
- PKCE verifier 必须真的送进 token 交换，且库里只存密文；
- state 绑定发起用户，回调落库归属不能被回调方指定；
- DCR 的 client_id 落库持久化：重启（新进程/新缓存）后读库复用同一 id。
"""

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet

from app.core.database import user_session
from app.domains.users.models import User
from app.models.mcp_oauth_state import McpOAuthState
from app.models.user_mcp_credential import UserMcpCredential
from app.services.mcp import oauth
from app.services.mcp.errors import McpAuthError
from app.services.mcp.oauth_client_store import read_client_id
from app.services.mcp.user_credentials import decrypt_payload, load_credential


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv('MCP_CREDENTIAL_KEY', Fernet.generate_key().decode('ascii'))
    monkeypatch.setenv('MCP_CREDENTIAL_KEY_VERSION', '1')
    monkeypatch.delenv('MCP_TZZB_CLIENT_ID', raising=False)
    monkeypatch.delenv('MCP_QIEMAN_CLIENT_ID', raising=False)
    monkeypatch.setenv('MCP_OAUTH_REDIRECT_URI', 'http://127.0.0.1:5000/api/mcp/oauth/callback/')


@pytest.fixture
def fake_upstream(monkeypatch):
    """上游 POST 打桩：DCR / token / revoke 分开计数。"""
    calls = []

    def fake_post(url, data, as_json=False):
        calls.append((url, dict(data), as_json))
        if url.endswith('/register'):
            return {'client_id': 'dcr-client-123'}
        if url.endswith('/token'):
            return {
                'access_token': 'fresh-access-token',
                'refresh_token': 'fresh-refresh-token',
                'expires_in': 3600,
                'token_type': 'Bearer',
            }
        if url.endswith('/revoke'):
            return {}
        raise AssertionError(f'未预期的上游地址：{url}')

    monkeypatch.setattr(oauth, '_http_post', fake_post)
    return calls


@pytest.fixture
def two_users(db):
    rows = []
    for name in ('oauth-a', 'oauth-b'):
        user = User(username=name, family_id=1)
        db.add(user)
        db.flush()
        rows.append(user.id)
    db.commit()
    return rows


def test_begin_qieman_uses_partner_gateway_and_minimal_scope(keys, fake_upstream, two_users):
    """且慢 OAuth：端点与 scope 来自实测元数据（#3304）——partner 域 + 最小权限。"""
    user_id, _ = two_users
    result = oauth.begin('qieman', user_id)
    parsed = urlparse(result['authorization_url'])

    assert parsed.netloc == 'stargate-partner.yingmi.com'
    assert parsed.path == '/oauth/authorize'
    params = parse_qs(parsed.query)
    assert params['scope'] == ['oapqieman:level1 offline_access']
    assert params['client_id'] == ['dcr-client-123']
    assert params['code_challenge_method'] == ['S256']
    assert params['resource'] == ['https://stargate-partner.yingmi.com/mcp/v2/oauth/qieman']


def test_qieman_token_requests_carry_same_resource_indicator(keys, fake_upstream, two_users):
    """RFC 8707 回归：且慢 authorize / code 换 token / refresh 必须指向同一资源。

    上游强制要求 authorize 携带 resource（缺则 invalid_target），token 端点
    同 RFC 也按资源限定 audience；只修 authorize 会在换 token 时再次失败。
    """
    user_id, _ = two_users
    resource = 'https://stargate-partner.yingmi.com/mcp/v2/oauth/qieman'

    result = oauth.begin('qieman', user_id)
    assert parse_qs(urlparse(result['authorization_url']).query)['resource'] == [resource]
    oauth.callback('qieman', result['state'], 'auth-code')
    oauth.refresh('qieman', user_id)

    token_calls = [data for url, data, _as_json in fake_upstream if url.endswith('/token')]
    assert len(token_calls) == 2
    assert all(data['resource'] == resource for data in token_calls)
    # DCR 不属于 RFC 8707 登记的参数位置，注册请求不能凭空多出 resource。
    registrations = [data for url, data, _as_json in fake_upstream if url.endswith('/register')]
    assert all('resource' not in data for data in registrations)


def test_begin_builds_s256_url_and_stores_encrypted_verifier(keys, fake_upstream, two_users):
    user_id, _ = two_users
    result = oauth.begin('tzzb', user_id)
    params = parse_qs(urlparse(result['authorization_url']).query)

    assert params['response_type'] == ['code']
    assert params['client_id'] == ['dcr-client-123']
    assert params['code_challenge_method'] == ['S256']
    assert params['scope'] == ['tools.read']
    assert params['state'] == [result['state']]

    with user_session() as session:
        row = session.query(McpOAuthState).filter_by(state=result['state']).one()
        assert row.user_id == user_id
        assert row.used_at is None
        assert 'verifier' not in row.verifier_cipher  # 存的是密文
        verifier = decrypt_payload(row.verifier_cipher, row.key_version)['verifier']
        assert verifier  # challenge 由它派生，下面回调用例还会核对


def test_callback_consumes_state_once_and_sends_pkce_verifier(keys, fake_upstream, two_users):
    user_id, _ = two_users
    result = oauth.begin('tzzb', user_id)
    with user_session() as session:
        row = session.query(McpOAuthState).filter_by(state=result['state']).one()
        verifier = decrypt_payload(row.verifier_cipher, row.key_version)['verifier']

    assert oauth.callback('tzzb', result['state'], 'auth-code-1') == user_id

    token_calls = [(data, as_json) for url, data, as_json in fake_upstream if url.endswith('/token')]
    assert len(token_calls) == 1
    # token 端点按 RFC 6749 必须 form 编码，与 DCR 的 JSON 相反。
    assert token_calls[0][1] is False
    assert token_calls[0][0]['grant_type'] == 'authorization_code'
    assert token_calls[0][0]['code_verifier'] == verifier
    assert token_calls[0][0]['code'] == 'auth-code-1'

    cred = load_credential(user_id, 'tzzb')
    assert cred.token == 'fresh-access-token'
    assert cred.refresh_token == 'fresh-refresh-token'

    # 变异探针：同一 state 再回调一次必须失败（重放防护）
    with pytest.raises(McpAuthError):
        oauth.callback('tzzb', result['state'], 'auth-code-2')


def test_expired_state_is_rejected(keys, fake_upstream, two_users):
    user_id, _ = two_users
    result = oauth.begin('tzzb', user_id)
    with user_session() as session:
        row = session.query(McpOAuthState).filter_by(state=result['state']).one()
        row.expires_at = oauth._now_naive() - timedelta(seconds=1)
        session.commit()

    with pytest.raises(McpAuthError):
        oauth.callback('tzzb', result['state'], 'auth-code')

    assert load_credential(user_id, 'tzzb') is None


def test_state_is_bound_to_provider(keys, fake_upstream, two_users, monkeypatch):
    """state 与 provider 绑定：拿同一 state 换另一家服务的 token 必须失败。"""
    user_id, _ = two_users
    result = oauth.begin('tzzb', user_id)
    other = oauth.PROVIDERS['tzzb']
    monkeypatch.setitem(oauth.PROVIDERS, 'tzzb-clone', other)
    with pytest.raises(McpAuthError):
        oauth.callback('tzzb-clone', result['state'], 'auth-code')


def test_dcr_registers_once(keys, fake_upstream, two_users):
    user_id, _ = two_users
    oauth.begin('tzzb', user_id)
    oauth.begin('tzzb', user_id)

    registrations = [(data, as_json) for url, data, as_json in fake_upstream if url.endswith('/register')]
    assert len(registrations) == 1
    # DCR 按 RFC 7591 必须发 JSON body（真机实证：form 编码被同花顺 400）。
    assert registrations[0][1] is True
    assert registrations[0][0]['token_endpoint_auth_method'] == 'none'
    # 注册结果落库（持久化）：重启后同一 provider 不再注册（红线见 oauth_client_store 测试）。
    assert read_client_id('tzzb') == 'dcr-client-123'


def test_refresh_replaces_access_token(keys, fake_upstream, two_users):
    user_id, _ = two_users
    result = oauth.begin('tzzb', user_id)
    oauth.callback('tzzb', result['state'], 'auth-code')

    oauth.refresh('tzzb', user_id)
    refresh_calls = [
        data
        for url, data, _as_json in fake_upstream
        if url.endswith('/token') and data['grant_type'] == 'refresh_token'
    ]
    assert len(refresh_calls) == 1
    assert refresh_calls[0]['refresh_token'] == 'fresh-refresh-token'
    assert load_credential(user_id, 'tzzb').token == 'fresh-access-token'


def test_revoke_deletes_local_credential(keys, fake_upstream, two_users):
    user_id, _ = two_users
    result = oauth.begin('tzzb', user_id)
    oauth.callback('tzzb', result['state'], 'auth-code')

    oauth.revoke('tzzb', user_id)

    assert load_credential(user_id, 'tzzb') is None
    assert any(url.endswith('/revoke') for url, _data, _as_json in fake_upstream)


def test_unknown_provider_never_builds_url(keys, fake_upstream, two_users):
    with pytest.raises(ValueError):
        oauth.begin('evil.example.com', two_users[0])
    assert fake_upstream == []


def test_expired_credential_can_still_refresh(keys, fake_upstream, two_users):
    """死锁回归：access_token 过期后 refresh_token 仍可读、可刷新。

    load_credential 默认对过期凭据抛错（resolve_token 链路的拦截口径），
    但 refresh 编排必须以 allow_expired=True 读取——否则过期凭据永远
    拿不到 refresh_token，只能重连（实测同花顺 access_token 仅 5 分钟寿命，
    过期是常态而非例外）。
    """
    user_id, _ = two_users
    result = oauth.begin('tzzb', user_id)
    oauth.callback('tzzb', result['state'], 'auth-code')

    with user_session() as session:
        row = session.query(UserMcpCredential).filter_by(user_id=user_id, provider='tzzb').one()
        row.expires_at = oauth._now_naive() - timedelta(seconds=1)
        session.commit()

    with pytest.raises(McpAuthError):
        load_credential(user_id, 'tzzb')  # 默认口径维持拦截

    oauth.refresh('tzzb', user_id)
    cred = load_credential(user_id, 'tzzb')
    assert cred is not None
    assert cred.token == 'fresh-access-token'


def test_expired_credential_can_still_revoke(keys, fake_upstream, two_users):
    """断开回归：授权过期的连接必须能断开（真机 500 复现）。

    revoke 的意图是「上游撤销失败不阻断本地删除」，但 load_credential 默认
    对过期凭据抛 McpAuthError，发生在撤销 try 块之外 ⇒ 断开按钮 500。
    过期恰恰是最需要断开的时刻（先断开才能重连），与刷新编排同款理由。
    """
    user_id, _ = two_users
    result = oauth.begin('tzzb', user_id)
    oauth.callback('tzzb', result['state'], 'auth-code')

    with user_session() as session:
        row = session.query(UserMcpCredential).filter_by(user_id=user_id, provider='tzzb').one()
        row.expires_at = oauth._now_naive() - timedelta(seconds=1)
        session.commit()

    oauth.revoke('tzzb', user_id)  # 修复前：此处抛 McpAuthError

    assert load_credential(user_id, 'tzzb', allow_expired=True) is None
    assert any(url.endswith('/revoke') for url, _data, _as_json in fake_upstream)

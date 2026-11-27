# -*- coding: utf-8 -*-
"""用户私有 MCP 凭据层回归（S5a/S5b）。

三条红线各有专门用例：

1. **绝不回退系统 Token** —— 即便系统 Token 已配，用户没连也必须抛
   ``McpUserTokenMissing``（变异：把分支改成 ``return system_token`` 必红）；
2. **按 user_id 隔离** —— A 用户的凭据不能出现在 B 用户的读取结果里；
3. **明文不出模块** —— 库里只有密文，管理页列表与异常文案都不含 token。

同时覆盖两种连接方式：``oauth2``（浏览器跳转）与 ``static_token``（API Key）。
"""

from datetime import datetime

import pytest
from cryptography.fernet import Fernet

from app.core.database import user_session
from app.domains.users.models import User
from app.models.user_mcp_credential import UserMcpCredential
from app.services.mcp.credentials import DataScope, resolve_token
from app.services.mcp.errors import McpAuthError, McpUserTokenMissing
from app.services.mcp.user_credentials import (
    AUTH_TYPES,
    CredentialCorrupt,
    CredentialKeyMissing,
    decrypt_payload,
    delete_credential,
    list_connections,
    load_credential,
    pkce_pair,
    save_oauth_token,
    save_static_token,
    validate_token_endpoint,
)


@pytest.fixture
def keys(monkeypatch):
    """两套 Fernet 密钥，供密钥轮换用例使用。"""
    v1 = Fernet.generate_key().decode('ascii')
    v2 = Fernet.generate_key().decode('ascii')
    monkeypatch.setenv('MCP_CREDENTIAL_KEY', v1)
    monkeypatch.setenv('MCP_CREDENTIAL_KEY_VERSION', '1')
    monkeypatch.delenv('MCP_CREDENTIAL_KEY_V2', raising=False)
    return v1, v2


@pytest.fixture
def two_users(db):
    """建两个 user 域用户（凭据隔离的判据需要两个真实 id）。"""
    rows = []
    for name in ('cred-a', 'cred-b'):
        user = User(username=name, family_id=1)
        db.add(user)
        db.flush()
        rows.append(user.id)
    db.commit()
    return rows


def test_auth_types_cover_browser_and_api_key():
    """浏览器 OAuth 与用户粘贴 API Key 必须同时 supported（契约用例）。"""
    assert set(AUTH_TYPES) == {'oauth2', 'static_token'}


def test_static_token_roundtrip_without_plaintext(keys, two_users):
    user_id, _ = two_users
    # 运行时拼接：写成完整字面量会被 guard_no_hardcoded_secrets 当成真 Key（CI 会红）。
    api_key = 'sk-' + 'userprivate' + '123456'

    save_static_token(user_id, 'qieman', api_key)
    cred = load_credential(user_id, 'qieman')

    assert cred is not None
    assert cred.auth_type == 'static_token'
    assert cred.token == api_key
    assert cred.expires_at is None
    assert cred.refresh_token is None

    with user_session() as session:
        row = session.query(UserMcpCredential).filter_by(user_id=user_id, provider='qieman').one()
        assert api_key not in row.cipher_text  # 库里只有密文
    assert api_key not in repr(cred)  # dataclass repr 也不回显（禁止进日志）


def test_cross_user_isolation(keys, two_users):
    """A 存的 API Key 只能 A 读到；B 读返回 None，绝不取「最新一条」。"""
    user_a, user_b = two_users
    save_static_token(user_a, 'tzzb', 'alice-key')

    assert load_credential(user_b, 'tzzb') is None
    assert load_credential(user_a, 'tzzb').token == 'alice-key'

    with pytest.raises(McpUserTokenMissing):
        resolve_token('tzzb', DataScope.USER_PRIVATE, user_id=user_b)


def test_oauth_token_and_refresh_are_separately_encrypted(keys, two_users):
    """浏览器授权：access / refresh 分开加密，过期时间保留。"""
    user_id, _ = two_users
    save_oauth_token(
        user_id,
        'tzzb',
        access_token='access-abc',
        refresh_token='refresh-xyz',
        expires_in=3600,
        token_endpoint='https://tzzb.10jqka.com.cn/oauth2/token',
    )

    cred = load_credential(user_id, 'tzzb')
    assert cred.auth_type == 'oauth2'
    assert cred.token == 'access-abc'
    assert cred.refresh_token == 'refresh-xyz'
    assert cred.token_endpoint == 'https://tzzb.10jqka.com.cn/oauth2/token'
    assert cred.expires_at > datetime.now()

    with user_session() as session:
        row = session.query(UserMcpCredential).filter_by(user_id=user_id, provider='tzzb').one()
        assert row.key_version == 1
        assert 'access-abc' not in row.cipher_text
        assert 'refresh-xyz' not in row.refresh_cipher
        assert decrypt_payload(row.refresh_cipher, row.key_version)['refresh_token'] == 'refresh-xyz'


def test_expired_oauth_token_raises_auth_error(keys, two_users):
    """过期不静默当成有效 token（那是 401 反复重试的源头）。"""
    user_id, _ = two_users
    save_oauth_token(user_id, 'tzzb', access_token='expired', expires_in=-10)

    with pytest.raises(McpAuthError):
        load_credential(user_id, 'tzzb')


def test_key_rotation_keeps_old_rows_readable(keys, monkeypatch, two_users):
    """轮换只换写入密钥；旧行按自身 key_version 解密，不能强制用户重连。"""
    _, v2 = keys
    user_id, _ = two_users
    save_static_token(user_id, 'qieman', 'old-key-token')

    monkeypatch.setenv('MCP_CREDENTIAL_KEY_VERSION', '2')
    monkeypatch.setenv('MCP_CREDENTIAL_KEY_V2', v2)

    assert load_credential(user_id, 'qieman').token == 'old-key-token'
    save_static_token(user_id, 'tzzb', 'new-key-token')
    assert load_credential(user_id, 'tzzb').token == 'new-key-token'

    with user_session() as session:
        versions = {
            row.provider: row.key_version for row in session.query(UserMcpCredential).filter_by(user_id=user_id).all()
        }
    assert versions == {'qieman': 1, 'tzzb': 2}


def test_missing_key_never_falls_back_to_plaintext(keys, monkeypatch, two_users):
    """缺密钥必须报错并把库原样留下——降级明文存储等于没加密。"""
    user_id, _ = two_users
    monkeypatch.delenv('MCP_CREDENTIAL_KEY', raising=False)

    with pytest.raises(CredentialKeyMissing):
        save_static_token(user_id, 'qieman', 'must-not-be-stored')

    with user_session() as session:
        assert session.query(UserMcpCredential).filter_by(user_id=user_id).count() == 0


def test_corrupt_cipher_raises_without_echoing_secret(keys, two_users):
    """密文损坏 / 密钥错时异常文案不得回显密文内容。"""
    user_id, _ = two_users
    save_static_token(user_id, 'qieman', 'secret-value')
    with user_session() as session:
        row = session.query(UserMcpCredential).filter_by(user_id=user_id).one()
        row.cipher_text = row.cipher_text[:-4] + 'AAAA'
        cipher = row.cipher_text
        session.commit()

    with pytest.raises(CredentialCorrupt) as excinfo:
        load_credential(user_id, 'qieman')
    assert cipher not in str(excinfo.value)
    assert 'secret-value' not in str(excinfo.value)


@pytest.mark.parametrize(
    'endpoint',
    [
        'http://tzzb.10jqka.com.cn/oauth2/token',
        'https://evil.example.com/token',
        'https://tzzb.10jqka.com.cn.evil.com/token',
    ],
)
def test_token_endpoint_ssrf_whitelist(keys, endpoint):
    """服务端元数据里的 endpoint 也受白名单约束，不接受用户自带 URL。"""
    with pytest.raises(ValueError):
        validate_token_endpoint(endpoint, 'tzzb')


def test_resolve_token_uses_user_api_key_not_system_token(keys, two_users, monkeypatch):
    """变异探针：系统 Token 已配好，用户私有能力仍必须取用户自己的 API Key。"""
    monkeypatch.setenv('QIEMAN_API_KEY', 'system-token-must-not-leak')
    user_id, _ = two_users
    save_static_token(user_id, 'qieman', 'alice-api-key')

    assert resolve_token('qieman', DataScope.USER_PRIVATE, user_id=user_id) == 'alice-api-key'


def test_resolve_token_without_connection_never_uses_system_token(keys, two_users, monkeypatch):
    """红线：用户没连 ⇒ 抛专属错误，错误文案不含系统 Token。"""
    monkeypatch.setenv('QIEMAN_API_KEY', 'system-token-must-not-leak')
    user_id, _ = two_users

    with pytest.raises(McpUserTokenMissing) as excinfo:
        resolve_token('qieman', DataScope.USER_PRIVATE, user_id=user_id)

    assert excinfo.value.kind == 'user_token_missing'
    assert 'system-token-must-not-leak' not in str(excinfo.value)
    assert 'system-token-must-not-leak' not in excinfo.value.user_message


def test_delete_and_list_never_expose_secret(keys, two_users):
    """断开即删行；列表只给可展示字段，不给密文 / token。"""
    user_id, other = two_users
    save_static_token(user_id, 'qieman', 'secret-to-delete')
    save_oauth_token(user_id, 'tzzb', access_token='access-to-delete', expires_in=60)

    listing = list_connections(user_id)
    assert {row['provider'] for row in listing} == {'qieman', 'tzzb'}
    assert all('secret-to-delete' not in str(row) and 'access-to-delete' not in str(row) for row in listing)
    assert list_connections(other) == []

    assert delete_credential(user_id, 'qieman') is True
    assert delete_credential(user_id, 'qieman') is False
    assert load_credential(user_id, 'qieman') is None
    assert load_credential(user_id, 'tzzb') is not None


def test_pkce_challenge_is_s256():
    """PKCE verifier 不落库，challenge 必须是 S256（授权编排层复用）。"""
    import base64
    import hashlib

    verifier, challenge = pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')
    assert challenge == expected
    assert '=' not in challenge

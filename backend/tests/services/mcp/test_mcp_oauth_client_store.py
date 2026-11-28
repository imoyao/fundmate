# -*- coding: utf-8 -*-
"""DCR client_id 持久化回归（``mcp_oauth_clients`` / ``oauth_client_store``）。

红线用例：

- **重启复用**：库里已有注册时，``client_id_for`` 不再向上游注册——
  这条是持久化的存在理由（refresh_token 绑定 client_id，换 id = 全员重连）；
- **并发竞态**：唯一约束下后写者保留先写者的注册（两个 id 都可用，
  但库里必须只剩一个真相源）；
- store 用独立短会话：不触碰请求级 ``user_session`` 的事务状态。
"""

import pytest
from cryptography.fernet import Fernet

from app.core.db_factory import user_session_factory
from app.models.mcp_oauth_client import McpOAuthClient
from app.services.mcp import oauth
from app.services.mcp.oauth_client_store import read_client_id, save_client_id


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv('MCP_CREDENTIAL_KEY', Fernet.generate_key().decode('ascii'))
    monkeypatch.setenv('MCP_CREDENTIAL_KEY_VERSION', '1')
    monkeypatch.delenv('MCP_TZZB_CLIENT_ID', raising=False)
    monkeypatch.setenv('MCP_OAUTH_REDIRECT_URI', 'http://127.0.0.1:5000/api/mcp/oauth/callback/')


def test_save_then_read_roundtrip():
    assert read_client_id('no-such-provider') is None
    assert save_client_id('roundtrip', 'cid-1') == 'cid-1'
    assert read_client_id('roundtrip') == 'cid-1'


def test_save_keeps_first_winner_on_race():
    """并发竞态：后写者不覆盖，返回先写者的 client_id。"""
    save_client_id('race', 'first-writer')
    returned = save_client_id('race', 'second-writer')
    assert returned == 'first-writer'
    assert read_client_id('race') == 'first-writer'
    rows = user_session_factory()().query(McpOAuthClient).filter(McpOAuthClient.provider == 'race').count()
    assert rows == 1


def test_save_rejects_blank_input():
    with pytest.raises(ValueError):
        save_client_id('', 'cid')
    with pytest.raises(ValueError):
        save_client_id('p', '')


def test_client_id_for_reuses_persisted_registration(keys, monkeypatch, db):
    """重启复用红线：库里已有注册 ⇒ 不打上游；env 预置仍最优先。"""

    def exploding_post(url, data, as_json=False):
        raise AssertionError('库里已有注册时不应调用上游 DCR')

    monkeypatch.setattr(oauth, '_http_post', exploding_post)
    save_client_id('tzzb', 'persisted-cid')

    config = oauth.provider_config('tzzb')
    assert oauth.client_id_for(config) == 'persisted-cid'

    # env 预置优先于库（运维改绑注册身份的逃生门）。
    monkeypatch.setenv('MCP_TZZB_CLIENT_ID', 'preset-cid')
    assert oauth.client_id_for(config) == 'preset-cid'


def test_client_id_for_persists_dcr_result(keys, monkeypatch, db):
    """DCR 成功后写库；库里残留旧行时以 save 返回值为准（竞态口径）。"""

    def fake_post(url, data, as_json=False):
        assert as_json is True
        return {'client_id': 'freshly-registered'}

    monkeypatch.setattr(oauth, '_http_post', fake_post)
    config = oauth.provider_config('tzzb')
    assert oauth.client_id_for(config) == 'freshly-registered'
    assert read_client_id('tzzb') == 'freshly-registered'

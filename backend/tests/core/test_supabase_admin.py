# -*- coding: utf-8 -*-
"""`app/core/supabase_admin.py` 单测（#2764 遗留项）。

关注三件事：
1. 未配置凭证时**不发起请求**、返回 False（本地/测试环境不能因为缺 key 就崩）；
2. 配好凭证后请求的 URL / 头部 / body 正确（这是唯一容易写错的部分）；
3. 任何失败（非 2xx、网络异常）都返回 False 而不是抛异常——调用方是「业务已成功，
   同步尽力而为」，抛出去会把一次成功的改名变成 500。
"""

import pytest

from app.core import supabase_admin


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://demo-ref.supabase.co/')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-role-key')


class _FakeResp:
    def __init__(self, status_code=200, text=''):
        self.status_code = status_code
        self.text = text


def test_is_configured_requires_both(monkeypatch):
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    assert supabase_admin.is_configured() is False

    monkeypatch.setenv('SUPABASE_URL', 'https://x.supabase.co')
    assert supabase_admin.is_configured() is False  # 缺 key 仍不算配好

    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'k')
    assert supabase_admin.is_configured() is True


def test_update_user_metadata_skips_without_credentials(monkeypatch):
    """未配置凭证必须**不发请求**——否则本地开发会一直打外部地址。"""
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)

    def _boom(*_a, **_k):
        raise AssertionError('未配置凭证时不应发起 HTTP 请求')

    monkeypatch.setattr(supabase_admin.requests, 'put', _boom)
    assert supabase_admin.update_user_metadata('sub-1', {'username': 'x'}) is False


def test_update_user_metadata_request_shape(configured, monkeypatch):
    seen = {}

    def _fake_put(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, json=json, timeout=timeout)
        return _FakeResp(200)

    monkeypatch.setattr(supabase_admin.requests, 'put', _fake_put)

    assert supabase_admin.update_user_metadata('sub-abc', {'username': 'newname'}) is True
    # URL 尾斜杠要被归一，否则拼出 `//auth/v1/...`
    assert seen['url'] == 'https://demo-ref.supabase.co/auth/v1/admin/users/sub-abc'
    assert seen['headers']['apikey'] == 'service-role-key'
    assert seen['headers']['Authorization'] == 'Bearer service-role-key'
    assert seen['json'] == {'user_metadata': {'username': 'newname'}}


def test_update_user_metadata_returns_false_on_4xx(configured, monkeypatch):
    monkeypatch.setattr(supabase_admin.requests, 'put', lambda *a, **k: _FakeResp(403, 'forbidden'))
    assert supabase_admin.update_user_metadata('sub-abc', {'username': 'x'}) is False


def test_update_user_metadata_swallows_network_error(configured, monkeypatch):
    def _boom(*_a, **_k):
        raise ConnectionError('network down')

    monkeypatch.setattr(supabase_admin.requests, 'put', _boom)
    assert supabase_admin.update_user_metadata('sub-abc', {'username': 'x'}) is False


def test_update_user_metadata_without_supabase_id(configured, monkeypatch):
    """本地种子用户 `supabase_id=None`：直接跳过，不拼出 `/users/None`。"""

    def _boom(*_a, **_k):
        raise AssertionError('supabase_id 为空时不应发起请求')

    monkeypatch.setattr(supabase_admin.requests, 'put', _boom)
    assert supabase_admin.update_user_metadata(None, {'username': 'x'}) is False


def test_revoke_session_request_shape(configured, monkeypatch):
    seen = {}

    def _fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, json=json)
        return _FakeResp(204)

    monkeypatch.setattr(supabase_admin.requests, 'post', _fake_post)

    assert supabase_admin.revoke_session('access-token-1') is True
    assert seen['url'] == 'https://demo-ref.supabase.co/auth/v1/logout'
    assert seen['json'] == {'access_token': 'access-token-1'}
    assert seen['headers']['apikey'] == 'service-role-key'


def test_revoke_session_returns_false_on_error(configured, monkeypatch):
    monkeypatch.setattr(supabase_admin.requests, 'post', lambda *a, **k: _FakeResp(401, 'bad token'))
    assert supabase_admin.revoke_session('access-token-1') is False


def test_revoke_session_skips_without_token(configured, monkeypatch):
    def _boom(*_a, **_k):
        raise AssertionError('没有 token 时不应发起请求')

    monkeypatch.setattr(supabase_admin.requests, 'post', _boom)
    assert supabase_admin.revoke_session('') is False

# -*- coding: utf-8 -*-
"""FeedLog SSO 令牌端点回归测试（#1998 任务 B）。

锁住三件最容易回归的事：

1. **未登录返回 200 + `{"token": null}`，绝不 401**——401 在前端
   `utils/http/index.ts` 的响应拦截器里会触发 `forceLogout()`，把「widget 顺手
   探测登录态」变成「用户被踢下线」。这条是卡面点名要验的反向验证项。
2. **降级路径不报错**：未配置 `FEEDLOG_SSO_SECRET`、用户没有邮箱 → 一样回
   `null`（缺配置是部署问题，不该让反馈面板报错）。
3. **viewer 只读角色拿得到令牌（GET）**——签发令牌没有任何写副作用，不该被
   D1 分权（写方法 403）挡住；GET 通道的存在就是为了这条。
"""

import jwt
import pytest

from app.domains.users.models import User
from app.services.feedlog import DEFAULT_TTL_SECONDS

SECRET = 'test-feedlog-sso-secret-key-32-bytes-min'


@pytest.fixture
def make_user(db):
    """造一个本地用户（X-User-Id 是中间件认的测试旁路头）。"""

    def _make(**kwargs):
        kwargs.setdefault('family_id', 1)
        kwargs.setdefault('username', 'feedlog-user')
        user = User(**kwargs)
        db.add(user)
        db.commit()
        return user

    return _make


def test_returns_null_token_when_not_signed_in(client):
    """未登录：200 + null（**不是 401**——401 会触发前端强制登出）。"""
    resp = client.get('/api/feedlog-token/')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()['data']['token'] is None


def test_issues_token_for_signed_in_user(client, make_user, monkeypatch):
    monkeypatch.setenv('FEEDLOG_SSO_SECRET', SECRET)
    user = make_user(email='u@example.com', nickname='阿明')
    resp = client.get('/api/feedlog-token/', headers={'X-User-Id': str(user.id)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    token = resp.get_json()['data']['token']
    assert token
    claims = jwt.decode(token, SECRET, algorithms=['HS256'])
    assert claims['email'] == 'u@example.com'
    assert claims['name'] == '阿明'
    assert claims['exp'] - claims['iat'] <= DEFAULT_TTL_SECONDS


def test_post_method_is_accepted_too(client, make_user, monkeypatch):
    """卡面写的是 POST——POST 必须同样可用。"""
    monkeypatch.setenv('FEEDLOG_SSO_SECRET', SECRET)
    user = make_user(email='u@example.com')
    resp = client.post('/api/feedlog-token/', headers={'X-User-Id': str(user.id)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()['data']['token']


def test_degrades_to_null_when_secret_not_configured(client, make_user, monkeypatch):
    """未配置 secret：降级为无身份，不报错。"""
    monkeypatch.delenv('FEEDLOG_SSO_SECRET', raising=False)
    user = make_user(email='u@example.com')
    resp = client.get('/api/feedlog-token/', headers={'X-User-Id': str(user.id)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()['data']['token'] is None


def test_degrades_to_null_when_user_has_no_email(client, make_user, monkeypatch):
    """用户没有邮箱 → 无法作为身份主键，诚实降级（不编造身份）。"""
    monkeypatch.setenv('FEEDLOG_SSO_SECRET', SECRET)
    user = make_user(email=None, username='no-email-user')
    resp = client.get('/api/feedlog-token/', headers={'X-User-Id': str(user.id)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()['data']['token'] is None


def test_viewer_role_can_read_token_via_get(client, make_user, monkeypatch):
    """viewer 只读角色：GET 拿得到令牌；POST 被 D1 分权拦下（403）。

    这条用例同时钉住「为什么两个方法都注册」——签发令牌没有写副作用，
    不该被写方法分权挡住。
    """
    monkeypatch.setenv('FEEDLOG_SSO_SECRET', SECRET)
    user = make_user(email='v@example.com', role='viewer')
    headers = {'X-User-Id': str(user.id)}

    resp_get = client.get('/api/feedlog-token/', headers=headers)
    assert resp_get.status_code == 200, resp_get.get_data(as_text=True)
    assert resp_get.get_json()['data']['token']

    resp_post = client.post('/api/feedlog-token/', headers=headers)
    assert resp_post.status_code == 403

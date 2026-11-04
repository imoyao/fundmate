# -*- coding: utf-8 -*-
"""FeedLog SSO 令牌签发的纯函数回归测试（#1998 任务 B）。

本文件锁住卡面写死的三条硬约束：
1. **`exp` 不得超过 24 小时**（FeedLog 消费端拒收更长的令牌）；
2. **secret 与 email 缺一不可**——secret 只存服务端，email 是身份主键；
3. **可选 claims（name / picture）缺省就不出现**（不写 null，避免消费端拿到
   「存在但为空」的字段）。
"""

import jwt
import pytest

from app.services.feedlog import DEFAULT_TTL_SECONDS, sign_feedlog_token

# 固定时间戳：断言 exp 的**数值**用固定 now 更清楚。
# decode 时关掉 exp 校验（该时间戳在 2023 年，已「过期」——但这里要验的是
# 「exp 被写成 now + 24h」这个数值，不是令牌此刻还有效）。
NOW = 1_700_000_000
SECRET = 'test-feedlog-sso-secret-key-32-bytes-min'


def test_signed_token_carries_email_and_bounded_exp():
    """claims 含 email；exp - iat 不超过 24 小时（卡面硬约束）。"""
    token = sign_feedlog_token(email='a@example.com', secret=SECRET, now=NOW)
    claims = jwt.decode(token, SECRET, algorithms=['HS256'], options={'verify_exp': False})
    assert claims['email'] == 'a@example.com'
    assert claims['iat'] == NOW
    assert claims['exp'] == NOW + DEFAULT_TTL_SECONDS
    assert claims['exp'] - claims['iat'] <= 24 * 3600


def test_optional_claims_are_omitted_when_blank():
    """name / picture 为空时**不写进 claims**（而不是写 null）。"""
    token = sign_feedlog_token(email='a@example.com', secret=SECRET, name='  ', picture='')
    claims = jwt.decode(token, SECRET, algorithms=['HS256'])
    assert 'name' not in claims
    assert 'picture' not in claims


def test_optional_claims_are_included_when_present():
    token = sign_feedlog_token(
        email='a@example.com',
        secret=SECRET,
        name=' 阿明 ',
        picture='https://cdn.example.com/a.png',
    )
    claims = jwt.decode(token, SECRET, algorithms=['HS256'])
    assert claims['name'] == '阿明'
    assert claims['picture'] == 'https://cdn.example.com/a.png'


def test_email_is_required():
    with pytest.raises(ValueError):
        sign_feedlog_token(email='   ', secret=SECRET)


def test_secret_is_required():
    with pytest.raises(ValueError):
        sign_feedlog_token(email='a@example.com', secret='  ')


def test_ttl_cannot_exceed_24_hours():
    """超过 24 小时的上限直接拒绝签发（而不是签出去让消费端拒收）。"""
    with pytest.raises(ValueError):
        sign_feedlog_token(email='a@example.com', secret=SECRET, ttl_seconds=DEFAULT_TTL_SECONDS + 1)


def test_token_verifies_only_with_the_workspace_secret():
    """别的密钥验不过——说明签发确实绑定到 workspace secret。"""
    token = sign_feedlog_token(email='a@example.com', secret=SECRET)
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, 'another-feedlog-secret-key-32-bytes-min', algorithms=['HS256'])

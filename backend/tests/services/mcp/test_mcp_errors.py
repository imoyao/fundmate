# -*- coding: utf-8 -*-
"""MCP 错误模型单测（S2，#2490）。

本文件钉住的是**判据**，不是文案：

- 8 个 kind 与 8 个子类**一一对应**（复制粘贴错一个就红）；
- ``McpError`` 必须是 ``RuntimeError`` —— S2 不靠改既有调用点/测试来"通过"；
- 429 默认按**频控**（可重试），仅报文含额度/欠费词才升级（Wind 真实报文尚未采样，
  不凭猜写死分类）；
- 欠费词**优先于**额度词（同时出现时人要做的事更重：联系服务商而不是等）；
- ``sanitize`` 必须抹掉凭据痕迹 —— 它是「Token 永不进日志」这条红线的实现位置，
  而最常见的泄漏形态是 dict repr / JSON 回显（``{'x-api-key': 'sk-…'}``）。
"""

import pytest

from app.services.mcp.errors import (
    McpAuthError,
    McpBadResponse,
    McpBillingError,
    McpError,
    McpErrorKind,
    McpQuotaExceeded,
    McpRateLimited,
    McpTokenMissing,
    McpUnavailable,
    McpUserTokenMissing,
    classify_exception,
    classify_http,
    classify_payload,
    display_name,
    sanitize,
)

#: 8 个子类 ↔ 8 个 kind 的对应表（新增一类时必须同时改这里，否则下面的用例会红）
_SUBCLASSES = (
    McpTokenMissing,
    McpUserTokenMissing,
    McpAuthError,
    McpQuotaExceeded,
    McpBillingError,
    McpRateLimited,
    McpUnavailable,
    McpBadResponse,
)


def test_kind_enum_has_exactly_eight_stable_values():
    """kind 的**值**是落库契约（``mcp_call_logs.error_kind``）与 health 判断依据，改名即破坏存量数据。"""
    assert {k.value for k in McpErrorKind} == {
        'token_missing',
        'user_token_missing',
        'auth',
        'quota',
        'billing',
        'rate_limit',
        'unavailable',
        'bad_response',
    }


def test_every_subclass_maps_to_a_distinct_kind():
    """子类与 kind 必须一一对应：多一个/少一个/重复一个都是接线错误。"""
    kinds = [cls.kind for cls in _SUBCLASSES]

    assert len(set(kinds)) == len(_SUBCLASSES), f'存在 kind 重复：{kinds}'
    assert set(kinds) == set(McpErrorKind)


@pytest.mark.parametrize(
    'cls,retryable,action',
    [
        (McpTokenMissing, False, 'configure_token'),
        (McpUserTokenMissing, False, 'configure_token'),
        (McpAuthError, False, 'configure_token'),
        (McpQuotaExceeded, False, 'wait'),
        (McpBillingError, False, 'contact'),
        (McpRateLimited, True, 'wait'),
        (McpUnavailable, True, 'wait'),
        (McpBadResponse, False, 'report'),
    ],
)
def test_retryable_and_action_per_kind(cls, retryable, action):
    """``retryable`` 决定要不要重试，``action`` 决定提示用户做什么 —— 两者都是对外语义。"""
    err = cls('detail')

    assert (err.retryable, err.action) == (retryable, action)


def test_mcp_error_is_runtime_error_for_backward_compat():
    """S2 的兼容承诺：既有 ``except RuntimeError`` / ``pytest.raises(RuntimeError)`` 仍然成立。"""
    assert issubclass(McpError, RuntimeError)

    with pytest.raises(RuntimeError):
        raise McpTokenMissing('未配置', provider='qieman')


@pytest.mark.parametrize(
    'provider,expected',
    [('qieman', '且慢'), ('wind', 'Wind'), ('newco', 'newco'), ('', 'MCP')],
)
def test_display_name(provider, expected):
    """未知 provider **原样返回**，不猜、不硬塞中文名（猜错会让日志指向另一家服务）。"""
    assert display_name(provider) == expected


def test_error_text_carries_kind_and_has_no_placeholder():
    """``str(exc)`` 带 kind（排查用）；``user_message`` 必须是**已格式化**的人话，不留占位符。"""
    err = McpAuthError('upstream said 401', provider='qieman')

    assert 'MCP[auth]' in str(err)
    assert '{who}' not in str(err)
    assert '{who}' not in err.user_message
    assert '且慢' in err.user_message


@pytest.mark.parametrize(
    'status,expected',
    [
        (401, McpAuthError),
        (403, McpAuthError),
        (402, McpBillingError),
        (500, McpUnavailable),
        (503, McpUnavailable),
        (400, McpBadResponse),
        (418, McpBadResponse),
    ],
)
def test_classify_http_mapping(status, expected):
    err = classify_http(status, 'upstream detail', provider='qieman')

    assert type(err) is expected
    assert err.http_status == status
    assert err.provider == 'qieman'


def test_429_defaults_to_retryable_rate_limit():
    """⚠️ 默认必须是**可重试的频控**：真实「额度用尽」报文尚未采样，猜死分类会把可恢复的抖动判成死局。"""
    err = classify_http(429, 'too many requests', provider='qieman')

    assert type(err) is McpRateLimited
    assert err.retryable is True


@pytest.mark.parametrize(
    'body,expected',
    [
        ('今日调用额度已用尽', McpQuotaExceeded),
        ('quota exceeded', McpQuotaExceeded),
        ('账户已欠费，请充值', McpBillingError),
        ('insufficient balance', McpBillingError),
    ],
)
def test_429_upgrades_kind_by_body_keywords(body, expected):
    err = classify_http(429, body, provider='wind')

    assert type(err) is expected
    assert err.http_status == 429


def test_billing_words_win_over_quota_words():
    """同时命中两族关键词 ⇒ 取**欠费**：它要求联系服务商，比「等额度恢复」更需要人介入。"""
    err = classify_http(429, '额度已用尽且账户欠费', provider='wind')

    assert type(err) is McpBillingError


def test_classify_payload_has_no_http_status():
    """上游 200 但 body 里带 error：没有状态码可依赖，只能按关键词判，兜底是 bad_response。"""
    assert type(classify_payload('quota exceeded')) is McpQuotaExceeded
    assert type(classify_payload('账户欠费')) is McpBillingError

    fallback = classify_payload('something odd happened')
    assert type(fallback) is McpBadResponse
    assert fallback.http_status is None


def test_classify_exception_returns_same_instance():
    """已是本家族的异常**原样返回**，不包一层 —— 包一层会把 http_status / kind 冲掉。"""
    err = McpAuthError('401', provider='qieman')

    assert classify_exception(err, provider='wind') is err


class ReadTimeout(Exception):
    """模拟 ``requests.ReadTimeout``：按**类名**判，避免 mcp 层硬依赖 requests。"""


def test_classify_exception_network_goes_unavailable_and_unknown_goes_bad_response():
    assert type(classify_exception(ReadTimeout('timed out'))) is McpUnavailable
    assert type(classify_exception(OSError('socket closed'))) is McpUnavailable
    assert type(classify_exception(ValueError('bad json'))) is McpBadResponse


def test_sanitize_masks_credentials_in_dict_repr_and_header_shape():
    """最常见的泄漏形态：dict repr / JSON 回显 / ``Authorization: Bearer …``。三者都要抹掉值。"""
    out = sanitize("{'x-api-key': 'sk-live-abcdef', 'Authorization': 'Bearer abc123'}")

    assert 'sk-live-abcdef' not in out
    assert 'abc123' not in out
    assert out.count('=***') >= 2


def test_sanitize_collapses_whitespace_and_truncates():
    flat = sanitize('line1\n\n  line2\t line3')

    assert flat == 'line1 line2 line3'

    long_text = 'x' * 500
    cut = sanitize(long_text, limit=20)
    assert len(cut) == 20
    assert cut.endswith('…')


def test_sanitize_keeps_ordinary_chinese_prose_intact():
    """反向加固：脱敏不得把正常报文（没有 ``key: value`` 形态）改坏，否则细节全丢。"""
    text = '且慢服务返回 503，请稍后重试'

    assert sanitize(text) == text

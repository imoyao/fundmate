# -*- coding: utf-8 -*-
"""`retry_policy`：429 三分类 / 处置 / 退避 / 话术（失败策略的单一真源）。

为什么单独测这份：它是**运行时重试判定**（`llm._classify_failure`）与 **CI 探针**
（`scripts/llm_health_probe.py`）共用的判据。两边对 `unknown` 的取舍刻意相反
（运行时可重试、探针按额度类），所以本模块只分类、不预设处置——这里钉「标签干净」，
处置策略由 `test_llm_backoff.py` 与 `scripts/tests/test_llm_health_probe.py` 各自钉。
"""

import pytest

from app.services.ai_recognizer import retry_policy


@pytest.mark.parametrize(
    ('body', 'expected_label', 'expected_code'),
    [
        # 额度/模型限额：方舟「安全体验模式」按模型封顶，重试无解
        ('{"error": {"code": "SetLimitExceeded"}}', retry_policy.QUOTA, 'SetLimitExceeded'),
        ('{"error": {"code": "QuotaExceeded"}}', retry_policy.QUOTA, 'QuotaExceeded'),
        # 码名不带 quota 但文案点了名（方舟 paused 文案）
        (
            '{"error": {"type": "SetLimitExceeded", "message": "model service has been paused"}}',
            retry_policy.QUOTA,
            'SetLimitExceeded',
        ),
        # 限流：等一等就会过
        ('{"error": {"code": "RateLimitExceeded"}}', retry_policy.RATE_LIMIT, 'RateLimitExceeded'),
        ('Too many requests, please slow down', retry_policy.RATE_LIMIT, ''),
        # 含 quota 字样的混合码按额度类：判据是词表匹配，不解析语法
        ('{"code": "Throttling.RateQuota"}', retry_policy.QUOTA, 'Throttling.RateQuota'),
        # 未知：既不点名额度也不像限流 —— 判据不替调用方选边
        ('{"error": {"code": "SomeBrandNewCode"}}', retry_policy.UNKNOWN, 'SomeBrandNewCode'),
        ('', retry_policy.UNKNOWN, ''),
    ],
)
def test_classify_429_labels(body, expected_label, expected_code):
    assert retry_policy.classify_429(body) == (expected_label, expected_code)


def test_rate_limit_wins_over_quota_when_both_words_present():
    """两类词同时出现时按限流（重试的代价更小）：判据顺序是契约的一部分。"""
    body = '{"error": {"code": "RateLimitExceeded", "message": "quota per minute exceeded"}}'
    assert retry_policy.classify_429(body)[0] == retry_policy.RATE_LIMIT


def test_error_code_survives_non_json_body():
    """非 JSON 响应体取不到码，返回空串而不是抛异常（调用方按标签走，不依赖码）。"""
    assert retry_policy.classify_429('QuotaExceeded: model paused') == (retry_policy.QUOTA, '')


class _Resp:
    """响应体鸭子类型桩：只要 `.text` / `.headers`。"""

    def __init__(self, text='', headers=None):
        self.text = text
        self.headers = headers or {}


def test_response_text_swallows_broken_stream():
    """读响应体失败（流已关闭/编码异常）返回空串：分类不该因读不到而抛。"""

    class Broken:
        @property
        def text(self):
            raise RuntimeError('stream closed')

    assert retry_policy.response_text(Broken()) == ''
    assert retry_policy.response_text(object()) == ''


@pytest.mark.parametrize(
    ('body', 'retryable', 'reason'),
    [
        ('{"error": {"code": "SetLimitExceeded"}}', False, 'quota:SetLimitExceeded'),
        ('', True, 'http=429'),  # 未知类：运行时可重试
        ('{"error": {"code": "RateLimitExceeded"}}', True, 'http=429'),
        ('{"error": {"code": "SomeBrandNewCode"}}', True, 'http=429'),
    ],
)
def test_retry_decision(body, retryable, reason):
    assert retry_policy.retry_decision(_Resp(body)) == (retryable, reason)


def test_backoff_honors_retry_after_with_cap():
    """Retry-After 认数值并封顶，非法值回落指数退避（防服务端回超大值挂死线程）。"""
    assert retry_policy.backoff_seconds(0, _Resp(headers={'Retry-After': '7'})) == 7.0
    capped = retry_policy.backoff_seconds(0, _Resp(headers={'Retry-After': '9999'}))
    assert capped == retry_policy.RETRY_AFTER_CAP_SECONDS
    assert retry_policy.backoff_seconds(2, _Resp(headers={'Retry-After': 'soon'})) == 6.0
    assert retry_policy.backoff_seconds(1) == 3.0


@pytest.mark.parametrize(
    ('reason', 'expected'),
    [
        ('quota:SetLimitExceeded', retry_policy.QUOTA_EXHAUSTED_MESSAGE),
        ('http=401', retry_policy.SERVICE_UNAVAILABLE_MESSAGE),
        ('', retry_policy.SERVICE_UNAVAILABLE_MESSAGE),
    ],
)
def test_failure_message_splits_quota_from_transient(reason, expected):
    """额度类话术不能含「稍后重试」：那是瞬态暗示，额度用尽时只会让用户再撞一次。"""
    message = retry_policy.failure_message(reason)
    assert message == expected
    if reason.startswith('quota'):
        assert '稍后重试' not in message

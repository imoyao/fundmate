# -*- coding: utf-8 -*-
"""call_llm 分类退避与 [llm.call] 结构化日志单测（#1121 S1-C）。

全离线：假 requests.post 按剧本返回/抛出，睡眠与 token 记账换成记录桩。
钉住设计约定：
- 429 分两层（2026-11-18）：额度/模型限额（`SetLimitExceeded`/`QuotaExceeded`）→ 立即终止、
  话术说「额度已用尽」；限流与未知类 → 可重试、话术保留「稍后重试」；
- 5xx / 超时 / 响应体异常 → 可重试，指数退避 1.5 / 3（ARK_RETRIES=2）；
- 其余 4xx（如 401）→ 立即终止，不重试不退避；
- 429 带数值型 Retry-After 头时听服务端的，无头/非法值回落指数退避；
- 重试耗尽 / 立即终止都抛 OCR_SERVICE_UNAVAILABLE（503，对外契约不变）；
- 首试成功不 sleep；成功行带 [llm.call] ok attempt=1；payload 可带 response_format。
"""

import json

import pytest
import requests
from loguru import logger

from app.core.exceptions import ErrorCode, SBException
from app.services.ai_recognizer import llm as llm_mod
from app.services.ai_recognizer import retry_policy


class FakeResponse:
    """仿 requests.Response：status_code + headers + raise_for_status/json/text。"""

    def __init__(self, status_code=200, body=None, headers=None, json_error=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self._json_error = json_error

    @property
    def text(self):
        """429 的分类判据读的是原始响应体（真实 requests 的 `.text`），不能只给 dict。"""
        if isinstance(self._body, str):
            return self._body
        return json.dumps(self._body or {})

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code} Error', response=self)

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._body


def _ok_body(content='ok', tokens=11):
    return {'choices': [{'message': {'content': content}}], 'usage': {'total_tokens': tokens}}


@pytest.fixture
def llm_env(monkeypatch):
    """隔离调用环境：key / 重试次数 / 睡眠 / token 记账全换可控桩。"""
    monkeypatch.setattr(llm_mod, 'ARK_API_KEY', 'sk-test')
    monkeypatch.setattr(llm_mod, 'ARK_RETRIES', 2)  # 共 3 次请求，退避序列 [1.5, 3.0]
    sleeps = []
    monkeypatch.setattr(llm_mod.time, 'sleep', sleeps.append)
    tokens = []
    monkeypatch.setattr(llm_mod, '_record_tokens', tokens.append)
    return sleeps, tokens


def _install_post(monkeypatch, script):
    """安装假 requests.post：按 script 依次返回/抛出（耗尽后重复最后一项），记录调用。"""

    def fake_post(url, **kwargs):
        fake_post.calls.append({'url': url, **kwargs})
        item = script[min(len(fake_post.calls) - 1, len(script) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    fake_post.calls = []
    monkeypatch.setattr(llm_mod.requests, 'post', fake_post)
    return fake_post.calls


def _call(**kwargs):
    return llm_mod.call_llm([{'type': 'text', 'text': 'hi'}], 'system', **kwargs)


def _capture(fn, level='INFO'):
    """执行 fn 并收集该过程内的 loguru 日志消息文本。"""
    captured = []
    hid = logger.add(lambda m: captured.append(str(m)), level=level)
    try:
        fn()
    finally:
        logger.remove(hid)
    return ''.join(captured)


# ── 首试成功：不 sleep、记账照旧、[llm.call] ok 留痕 ──
def test_success_first_try_no_sleep(llm_env, monkeypatch):
    sleeps, tokens = llm_env
    calls = _install_post(monkeypatch, [FakeResponse(body=_ok_body('识别结果', 42))])
    out = None
    captured = []
    hid = logger.add(lambda m: captured.append(str(m)), level='INFO')
    try:
        out = _call()
    finally:
        logger.remove(hid)
    assert out == '识别结果'
    assert sleeps == []  # 首试成功不 sleep
    assert len(calls) == 1
    assert tokens == [42]  # 费用记账照旧
    line = next(m for m in captured if '[llm.call]' in m)
    assert 'ok attempt=1' in line
    assert 'tokens=42' in line


# ── 其余 4xx（401）：立即终止，不重试不退避 ──
def test_401_fail_fast_no_retry(llm_env, monkeypatch):
    sleeps, _ = llm_env
    calls = _install_post(monkeypatch, [FakeResponse(status_code=401)])
    with pytest.raises(SBException) as exc:
        _call()
    assert exc.value.code == ErrorCode.OCR_SERVICE_UNAVAILABLE.code
    assert len(calls) == 1  # 坏请求重试无意义：只打一次
    assert sleeps == []


# ── 5xx：指数退避 [1.5, 3.0] 后耗尽 → 503 ──
def test_5xx_exponential_backoff(llm_env, monkeypatch):
    sleeps, _ = llm_env
    calls = _install_post(monkeypatch, [FakeResponse(status_code=502)])

    def _expect_fail():
        with pytest.raises(SBException):
            _call()

    joined = _capture(_expect_fail, level='WARNING')
    assert len(calls) == 3  # ARK_RETRIES=2 → 3 次请求
    assert sleeps == [1.5, 3.0]  # base 1.5 指数退避
    assert '[llm.call] retry attempt=1/2 reason=http=502 backoff=1.50s' in joined
    assert '[llm.call] fail attempts=3' in joined


# ── 429：认 Retry-After 头 ──
def test_429_honors_retry_after(llm_env, monkeypatch):
    sleeps, _ = llm_env
    _install_post(
        monkeypatch,
        [
            FakeResponse(status_code=429, headers={'Retry-After': '4'}),
            FakeResponse(body=_ok_body()),
        ],
    )
    assert _call() == 'ok'
    assert sleeps == [4.0]


# ── 429 无头：回落指数退避 ──
def test_429_without_header_falls_back(llm_env, monkeypatch):
    sleeps, _ = llm_env
    _install_post(
        monkeypatch,
        [
            FakeResponse(status_code=429),
            FakeResponse(status_code=429),
            FakeResponse(body=_ok_body()),
        ],
    )
    assert _call() == 'ok'
    assert sleeps == [1.5, 3.0]


# ── 429 额度/模型限额：终止态，不重试，话术不承诺「稍后重试」（2026-11-18） ──
_QUOTA_BODY = {
    'error': {
        'code': 'SetLimitExceeded',
        'message': 'The model service has been paused. Please check the model service status.',
    }
}


def test_429_quota_is_terminal_no_retry(llm_env, monkeypatch):
    """`SetLimitExceeded` 重试必然再失败：只打一次、不 sleep、日志标 quota。

    旧实现把所有 429 都当瞬态，`bench-01..03` 每条白打 2 次请求；
    本用例在 `ARK_RETRIES=2` 下断言 calls==1，回退实现会变成 3。
    """
    sleeps, _ = llm_env
    calls = _install_post(monkeypatch, [FakeResponse(status_code=429, body=_QUOTA_BODY)])

    def _expect_fail():
        with pytest.raises(SBException):
            _call()

    joined = _capture(_expect_fail, level='WARNING')
    assert len(calls) == 1  # 终止态：不打第二次
    assert sleeps == []  # 也不退避
    assert 'reason=quota:SetLimitExceeded' in joined  # 错误码进日志，排障能直接归因


def test_429_quota_message_says_quota_not_retry_later(llm_env, monkeypatch):
    """对外话术分开：额度类说「额度已用尽」，不能说「请稍后重试」（瞬态暗示）。"""
    _install_post(monkeypatch, [FakeResponse(status_code=429, body=_QUOTA_BODY)])
    with pytest.raises(SBException) as exc:
        _call()
    assert exc.value.code == ErrorCode.OCR_SERVICE_UNAVAILABLE.code  # 对外错误码不变
    assert exc.value.status_code == ErrorCode.OCR_SERVICE_UNAVAILABLE.http_status
    assert exc.value.message == retry_policy.QUOTA_EXHAUSTED_MESSAGE
    assert '稍后重试' not in exc.value.message


def test_429_quota_in_plain_text_body_is_terminal(llm_env, monkeypatch):
    """网关可能只回一行纯文本（非 JSON）：读不出错误码也要认出额度类。"""
    body = 'QuotaExceeded: model service has been paused'
    calls = _install_post(monkeypatch, [FakeResponse(status_code=429, body=body)])
    with pytest.raises(SBException) as exc:
        _call()
    assert len(calls) == 1
    assert exc.value.message == retry_policy.QUOTA_EXHAUSTED_MESSAGE


def test_429_rate_limit_keeps_retry_and_transient_copy(llm_env, monkeypatch):
    """限流类维持原语义：可重试；重试耗尽后仍是「请稍后重试」（等一等确实会过）。"""
    sleeps, _ = llm_env
    calls = _install_post(
        monkeypatch,
        [FakeResponse(status_code=429, body={'error': {'code': 'RateLimitExceeded'}})],
    )
    with pytest.raises(SBException) as exc:
        _call()
    assert len(calls) == 3  # ARK_RETRIES=2 → 3 次
    assert sleeps == [1.5, 3.0]
    assert exc.value.message == retry_policy.SERVICE_UNAVAILABLE_MESSAGE


def test_429_unknown_body_still_retried(llm_env, monkeypatch):
    """未知类（新错误码 / 响应体读不到）按可重试处理：漏判多一次请求 < 误判白丢请求。"""
    sleeps, _ = llm_env
    calls = _install_post(
        monkeypatch,
        [
            FakeResponse(status_code=429, body={'error': {'code': 'SomeBrandNewCode'}}),
            FakeResponse(body=_ok_body()),
        ],
    )
    assert _call() == 'ok'
    assert len(calls) == 2
    assert sleeps == [1.5]


# ── 超时耗尽：503（对外契约不变） ──
def test_timeout_exhausted_raises_service_unavailable(llm_env, monkeypatch):
    sleeps, _ = llm_env
    calls = _install_post(monkeypatch, [requests.Timeout('read timeout')])
    with pytest.raises(SBException) as exc:
        _call()
    assert exc.value.code == ErrorCode.OCR_SERVICE_UNAVAILABLE.code
    assert len(calls) == 3
    assert sleeps == [1.5, 3.0]


# ── 响应体异常：坏 JSON / 空 choices 都可重试 ──
def test_bad_json_body_retried(llm_env, monkeypatch):
    sleeps, _ = llm_env
    _install_post(
        monkeypatch,
        [
            FakeResponse(json_error=ValueError('Expecting value')),
            FakeResponse(body=_ok_body()),
        ],
    )
    assert _call() == 'ok'
    assert sleeps == [1.5]


def test_empty_choices_retried(llm_env, monkeypatch):
    sleeps, _ = llm_env
    _install_post(
        monkeypatch,
        [
            FakeResponse(body={'choices': [], 'usage': {'total_tokens': 0}}),
            FakeResponse(body=_ok_body()),
        ],
    )
    assert _call() == 'ok'
    assert sleeps == [1.5]


# ── payload：显式传入时带 response_format，缺省不带 ──
def test_payload_carries_response_format(llm_env, monkeypatch):
    calls = _install_post(monkeypatch, [FakeResponse(body=_ok_body())])
    _call(response_format={'type': 'json_object'})
    assert calls[0]['json']['response_format'] == {'type': 'json_object'}
    _call()
    assert 'response_format' not in calls[1]['json']

# -*- coding: utf-8 -*-
"""call_llm 分类退避与 [llm.call] 结构化日志单测（#1121 S1-C）。

全离线：假 requests.post 按剧本返回/抛出，睡眠与 token 记账换成记录桩。
钉住设计约定：
- 429 / 5xx / 超时 / 响应体异常 → 可重试，指数退避 1.5 / 3（ARK_RETRIES=2）；
- 其余 4xx（如 401）→ 立即终止，不重试不退避；
- 429 带数值型 Retry-After 头时听服务端的，无头/非法值回落指数退避；
- 重试耗尽 / 立即终止都抛 OCR_SERVICE_UNAVAILABLE（503，对外契约不变）；
- 首试成功不 sleep；成功行带 [llm.call] ok attempt=1；payload 可带 response_format。
"""

import pytest
import requests
from loguru import logger

from app.core.exceptions import ErrorCode, SBException
from app.services.ai_recognizer import llm as llm_mod


class FakeResponse:
    """仿 requests.Response：status_code + headers + raise_for_status/json。"""

    def __init__(self, status_code=200, body=None, headers=None, json_error=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self._json_error = json_error

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

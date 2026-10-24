# -*- coding: utf-8 -*-
"""`app/core/requests_patch.py` 的默认超时回归网（#2506）。

事故形态：上游「连上了但不回数据」时，requests 会**无限期**等下去——
重试救不了这种情况（重试只在连接失败/读错误时触发，挂在读上的死等不会重来）。
实测每日调度在第一个 job「stock_list」上**卡了 23 分钟没有任何日志**，
最终被 workflow 的 30 分钟 job 超时掐掉，整条数据新鲜度链路一天都没跑成，
而且日志里看不出它卡在哪。

本文件钉住三条：
- 调用方**没传** timeout ⇒ 补上默认超时（挂住的上游变成「这个源失败」）；
- 调用方**显式传了** timeout ⇒ 原样保留（不剥夺调用方的选择权）；
- 调用方**显式传 timeout=None**（表示「不限时」）⇒ 也不动。
"""

from app.core import requests_patch


class _Recorder:
    """假 original：只记录 kwargs，不发真实请求。"""

    def __init__(self):
        self.calls = []

    def __call__(self, session, method, url, *args, **kwargs):
        self.calls.append({'method': method, 'url': url, **kwargs})
        return 'ok'


def _wrapped(recorder):
    return requests_patch._wrap_request(recorder)


def test_missing_timeout_gets_default():
    recorder = _Recorder()
    _wrapped(recorder)('session', 'GET', 'https://example.com/x')
    assert recorder.calls[0]['timeout'] == requests_patch._DEFAULT_TIMEOUT_SECONDS


def test_explicit_timeout_is_preserved():
    recorder = _Recorder()
    _wrapped(recorder)('session', 'GET', 'https://example.com/x', timeout=5)
    assert recorder.calls[0]['timeout'] == 5


def test_explicit_none_means_unbounded_and_is_kept():
    """显式 timeout=None 是调用方在说「不限时」——不能被我们改掉。"""
    recorder = _Recorder()
    _wrapped(recorder)('session', 'GET', 'https://example.com/x', timeout=None)
    assert recorder.calls[0]['timeout'] is None


def test_default_timeout_is_configurable(monkeypatch):
    monkeypatch.setenv('FUNDMATE_HTTP_TIMEOUT', '90')
    recorder = _Recorder()
    _wrapped(recorder)('session', 'GET', 'https://example.com/x')
    assert recorder.calls[0]['timeout'] == 90.0


def test_invalid_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv('FUNDMATE_HTTP_TIMEOUT', 'abc')
    assert requests_patch._default_timeout() == requests_patch._DEFAULT_TIMEOUT_SECONDS

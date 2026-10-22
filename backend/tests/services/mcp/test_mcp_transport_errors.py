# -*- coding: utf-8 -*-
"""MCP 传输层的**失败语义与记账**（S2，#2490）。

S1 的 ``test_mcp_transport.py`` 钉的是会话复用 / SSE 解析 / 请求形状；
``test_qieman_batch_transport.py`` 通过真实适配器钉批量链路。本文件只补 S2 新增的两件事：

1. **失败必须类型化**：``_post`` 是调用方注入的回调，它抛出的网络异常、
   以及任何未知异常，都不经过状态码分支 —— 若原样漏出去，job 层的 ``except McpError``
   （按平台隔离）就抓不到，一个平台抖动会重新升级成整轮失败；
2. **记账在唯一入口**：``capability`` 传了才写 ``mcp_call_logs``（纯协议单测因此不触库），
   一次"能力调用"一行（含重握重试），不是一次 HTTP 一行。
"""

import pytest

from app.services.mcp import McpTransport
from app.services.mcp.credentials import DataScope
from app.services.mcp.errors import McpAuthError, McpBadResponse, McpQuotaExceeded, McpRateLimited, McpUnavailable

_PROVIDER = 'qieman'


class _Resp:
    """``requests.Response`` 的最小替身（只实现传输层用到的成员）。"""

    def __init__(self, status_code=200, headers=None, payload=None, lines=None, body=''):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload
        self._lines = lines
        self.text = body

    def json(self):
        if self._payload is None:
            raise ValueError('Expecting value: line 1 column 1 (char 0)')
        return self._payload

    def iter_lines(self, decode_unicode=True):
        return iter(self._lines or [])


def _json_ok(text: str = 'ok') -> _Resp:
    return _Resp(
        headers={'content-type': 'application/json'},
        payload={'jsonrpc': '2.0', 'id': 2, 'result': {'content': [{'type': 'text', 'text': text}]}},
    )


class _Provider:
    """provider 替身：传输层读 ``protocol_version`` / ``client_info`` / ``_wire`` / ``name``。"""

    name = _PROVIDER
    protocol_version = '2024-11-05'
    client_info = {'name': 'test', 'version': '0'}

    def _wire(self, tool, arguments):
        return {
            'jsonrpc': '2.0',
            'id': 2,
            'method': 'tools/call',
            'params': {'name': tool, 'arguments': arguments},
        }


class _Post:
    """按脚本返回响应；``tools`` 用完后重复最后一项（便于构造"两次都失败"）。"""

    def __init__(self, tools, *, notify_status=200):
        self.methods = []
        self._tools = list(tools)
        self._notify_status = notify_status

    def __call__(self, payload, sid):
        method = payload.get('method')
        self.methods.append(method)
        if method == 'initialize':
            return _Resp(headers={})
        if method == 'notifications/initialized':
            return _Resp(status_code=self._notify_status)
        return self._tools.pop(0) if len(self._tools) > 1 else self._tools[0]


def _transport(post) -> McpTransport:
    return McpTransport(post, _Provider())


def _audit_rows():
    from app.core.database import market_session
    from app.models.mcp_call_log import McpCallLog

    with market_session() as db:
        return db.query(McpCallLog).filter(McpCallLog.provider == _PROVIDER).all()


# ── 失败类型化 ──


@pytest.mark.parametrize('status,expected', [(401, McpAuthError), (403, McpAuthError), (500, McpUnavailable)])
def test_http_status_is_classified(status, expected):
    t = _transport(_Post([_Resp(status_code=status, body=f'HTTP {status}')]))

    with pytest.raises(expected) as excinfo:
        t.call_tool('SomeTool', {}, token='k')

    assert excinfo.value.http_status == status
    assert excinfo.value.provider == _PROVIDER


def test_429_is_rate_limited_unless_body_says_quota():
    """默认频控（可重试）；报文明确说额度用尽才升级为不可重试。"""
    t = _transport(_Post([_Resp(status_code=429, body='too many requests')]))
    with pytest.raises(McpRateLimited) as excinfo:
        t.call_tool('SomeTool', {}, token='k')
    assert excinfo.value.retryable is True

    t2 = _transport(_Post([_Resp(status_code=429, body='今日调用额度已用尽')]))
    with pytest.raises(McpQuotaExceeded):
        t2.call_tool('SomeTool', {}, token='k')


def test_network_exception_from_post_becomes_typed_error():
    """``_post`` 抛网络异常（不起状态码分支）⇒ 必须归一为 ``McpUnavailable``，不得裸着漏出去。"""

    def _post(payload, sid):
        raise ConnectionError('connection reset by peer')

    with pytest.raises(McpUnavailable) as excinfo:
        _transport(_post).call_tool('SomeTool', {}, token='k')

    assert 'connection reset' in excinfo.value.detail


def test_unknown_exception_from_post_becomes_bad_response():
    """未知异常归 ``bad_response``（重试无意义、要人看），同样不得裸着漏出去。"""

    def _post(payload, sid):
        raise RuntimeError('weird internal state')

    with pytest.raises(McpBadResponse):
        _transport(_post).call_tool('SomeTool', {}, token='k')


def test_session_invalid_retries_once_then_bad_response():
    """400/404 = 会话失效：重握一次再试；两次都失效才抛，且明确说是"重握后仍失败"。"""
    post = _Post([_Resp(status_code=404, body='session gone')])
    t = _transport(post)

    with pytest.raises(McpBadResponse, match='会话重握后仍失败'):
        t.call_tool('SomeTool', {}, token='k')

    assert post.methods.count('initialize') == 2, '只允许重握一次'


def test_payload_error_field_is_classified():
    """200 但 body 带 error：没有状态码可依赖，按关键词判。"""
    post = _Post(
        [
            _Resp(
                headers={'content-type': 'application/json'},
                payload={'jsonrpc': '2.0', 'id': 2, 'error': {'message': 'quota exceeded'}},
            )
        ]
    )

    with pytest.raises(McpQuotaExceeded):
        _transport(post).call_tool('SomeTool', {}, token='k')


def test_empty_content_is_not_silently_empty():
    """空结果必须抛 ``bad_response``：静默返回空串会被上层读成「这只组合没有持仓」。"""
    post = _Post(
        [
            _Resp(
                headers={'content-type': 'application/json'},
                payload={'jsonrpc': '2.0', 'id': 2, 'result': {'content': []}},
            )
        ]
    )

    with pytest.raises(McpBadResponse, match='调用返回为空'):
        _transport(post).call_tool('SomeTool', {}, token='k')


# ── 记账（唯一入口）──


def test_no_capability_means_no_audit_row():
    """纯协议单测不传 capability ⇒ 不触碰数据库。这是"抽象只在有读者时才建"的落点。"""
    t = _transport(_Post([_json_ok()]))

    assert t.call_tool('SomeTool', {}, token='k') == 'ok'
    assert _audit_rows() == []


def test_success_writes_exactly_one_row_with_scope():
    t = _transport(_Post([_json_ok()]))

    t.call_tool('SomeTool', {}, token='k', capability='strategy_composition', scope=DataScope.PLATFORM_PUBLIC)

    rows = _audit_rows()
    assert len(rows) == 1
    assert rows[0].ok is True
    assert rows[0].capability == 'strategy_composition'
    assert rows[0].scope == 'platform_public'


def test_failure_writes_exactly_one_row_with_error_kind():
    """含重握重试在内只记**一行**：记账粒度是"能力调用"，不是 HTTP 请求。"""
    post = _Post([_Resp(status_code=404), _Resp(status_code=401, body='bad token')])
    t = _transport(post)

    with pytest.raises(McpAuthError):
        t.call_tool('SomeTool', {}, token='k', capability='strategy_composition')

    rows = _audit_rows()
    assert len(rows) == 1
    assert rows[0].ok is False
    assert rows[0].error_kind == 'auth'
    assert rows[0].http_status == 401

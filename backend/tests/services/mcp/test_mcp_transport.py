# -*- coding: utf-8 -*-
"""MCP 传输层单测（#2488，S1）。

会话复用 / 失效重握 / 批量这三件已在 ``tests/services/thermometer/test_qieman_batch_transport.py``
里**通过且慢适配器**钉住（那条链路是真实调用方，别在这里重复一遍）。本文件只补三件
那条链路覆盖不到的事：

1. ``text/event-stream`` 响应解析 —— 真实上游会走 SSE，但既有用例的替身一律返回 JSON；
2. ``notifications/initialized`` 非 2xx 必须抛错**且不重试**（重试只针对会话失效；
   若把这条也当成会话失效，一次握手失败会被放大成两倍请求）；
3. **请求形状来自 ``provider._wire``** —— S3 的 Wind 覆盖它就能换请求体，
   不必改 ``transport.py``；这条用例是那个承诺的判据。

全部替身，不联网、不读真实凭据。
"""

import pytest

from app.services.mcp import McpTransport
from app.services.mcp.errors import McpBadResponse, McpUnavailable


class _Resp:
    """``requests.Response`` 的最小替身（只实现传输层用到的成员）。"""

    def __init__(self, status_code=200, headers=None, payload=None, lines=None, bad_json=False, content=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload
        self._lines = lines
        self._bad_json = bad_json
        if content is not None:
            self.content = content
        elif lines is not None:
            # 传输层现在按原始字节 + UTF-8 解码（``resp.text`` 会被 requests 猜成
            # ISO-8859-1，把中文折成两行），故替身也要给 ``content``。
            self.content = '\n'.join(lines).encode('utf-8')
        else:
            self.content = b''

    def json(self):
        if self._bad_json:
            raise ValueError('Expecting value: line 1 column 1 (char 0)')
        return self._payload

    def iter_lines(self, decode_unicode=True):
        return iter(self._lines or [])


def _json_ok(text: str) -> _Resp:
    """``tools/call`` 正常响应（content-type: application/json）。"""
    return _Resp(
        headers={'content-type': 'application/json'},
        payload={'jsonrpc': '2.0', 'id': 2, 'result': {'content': [{'type': 'text', 'text': text}]}},
    )


class _Provider:
    """provider 替身：只提供传输层读得到的三个成员。"""

    protocol_version = '2024-11-05'
    client_info = {'name': 'test', 'version': '0'}

    def __init__(self, wire=None):
        self._wire_override = wire
        self.wired = []

    def _wire(self, tool, arguments):
        self.wired.append((tool, arguments))
        if self._wire_override is not None:
            return self._wire_override(tool, arguments)
        return {
            'jsonrpc': '2.0',
            'id': 2,
            'method': 'tools/call',
            'params': {'name': tool, 'arguments': arguments},
        }


class _Post:
    """替换 ``post`` 回调：按 method 分派，并记录收到的载荷与调用序列。"""

    def __init__(self, tools, *, sid=None, notify_status=200):
        self.sent = []  # 收到的完整 payload 列表
        self.methods = []  # 调用序列（method 名）
        self._tools = list(tools)
        self._sid = sid
        self._notify_status = notify_status

    def __call__(self, payload, sid):
        self.sent.append(payload)
        method = payload.get('method')
        self.methods.append(method)
        if method == 'initialize':
            return _Resp(headers={} if self._sid is None else {'Mcp-Session-Id': self._sid})
        if method == 'notifications/initialized':
            return _Resp(status_code=self._notify_status)
        return self._tools.pop(0) if len(self._tools) > 1 else self._tools[0]


def test_sse_response_is_parsed():
    """SSE：只认 ``id == 2`` 的那条消息，其余（不合法的 data 行 / 别的 id）跳过。"""
    lines = [
        'data: not-json',
        'event: ping',
        'data: {"jsonrpc":"2.0","id":1,"result":{"content":[]}}',
        'data: {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"来自SSE"}]}}',
        '',
    ]
    post = _Post([_Resp(headers={'content-type': 'text/event-stream'}, lines=lines)])
    transport = McpTransport(post, _Provider())

    assert transport.call_tool('SomeTool', {}, token='k') == '来自SSE'
    assert post.methods == ['initialize', 'notifications/initialized', 'tools/call']


def test_sse_line_with_event_and_data_on_one_line_is_parsed():
    """实测（2026-10-23）：上游把 ``event:`` 与 ``data:`` 放在**同一行**。

    按「行首是否 ``data:``」匹配会一条都取不到 ⇒ 最终报「调用返回为空」，
    一个看起来像「上游没数据」的假结论。故用行内首次出现 ``data:`` 定位。
    """
    lines = ['event: message data: {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"同一行"}]}}']
    post = _Post([_Resp(headers={'content-type': 'text/event-stream'}, lines=lines)])

    assert McpTransport(post, _Provider()).call_tool('SomeTool', {}, token='k') == '同一行'


def test_sse_utf8_continuation_byte_is_not_treated_as_line_break():
    """UTF-8 续字节 ``0x85``（U+0085 NEXT LINE）不得被当成换行。

    实测（2026-10-23，真实网关）：``text/event-stream`` 不带 charset ⇒ requests 猜
    **ISO-8859-1** ⇒ 中文的某个续字节变成 U+0085，``iter_lines`` / ``str.splitlines()``
    在那里把一行 JSON 折断 ⇒ ``json.loads`` 全失败 ⇒ 上层读成「调用返回为空」
    （一个看起来像「上游没数据」的假结论）。故必须拿原始字节按 UTF-8 解码。
    """
    body = (
        b'event: message\r\n'
        b'data: {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"\xe4\xb8\x85"}]}}\r\n'
        b'\r\n'
    )
    post = _Post([_Resp(headers={'content-type': 'text/event-stream'}, content=body)])

    assert McpTransport(post, _Provider()).call_tool('SomeTool', {}, token='k') == '丅'


def test_sse_without_matching_message_raises():
    """SSE 里没有匹配消息 ⇒ 视为空结果，抛**类型化**错误而不是静默返回空串。

    S2 起断言类型而不只是文案：``McpBadResponse`` 是「重试无意义、要人看」的那一类，
    正是这条路径的语义（原断言只钉了字符串，换文案就会静默通过）。
    """
    post = _Post([_Resp(headers={'content-type': 'text/event-stream'}, lines=['data: {"id":9}'])])
    transport = McpTransport(post, _Provider())

    with pytest.raises(McpBadResponse):
        transport.call_tool('SomeTool', {}, token='k')


def test_initialized_notification_failure_raises_without_retry():
    """``notifications/initialized`` 失败：抛错且**不重试**（重试只服务于会话失效）。

    S2 起错误带上 ``http_status``：``500`` ⇒ ``McpUnavailable``（可重试的那一类，
    由 job 层决定是否重试，而不是在传输层循环）。
    """
    post = _Post([_json_ok('never')], notify_status=500)
    transport = McpTransport(post, _Provider())

    with pytest.raises(McpUnavailable) as excinfo:
        transport.call_tool('SomeTool', {}, token='k')
    assert excinfo.value.http_status == 500
    assert post.methods == ['initialize', 'notifications/initialized']


def test_request_shape_comes_from_provider_wire():
    """请求体由 ``provider._wire`` 决定（S3 接 Wind 的扩展点，不改传输层）。"""
    custom = {'toolName': 'WindTool', 'arguments': '{"a":1}'}
    provider = _Provider(wire=lambda tool, arguments: custom)
    post = _Post([_json_ok('ok')])

    assert McpTransport(post, provider).call_tool('SomeTool', {'a': 1}, token='k') == 'ok'
    assert post.sent[-1] is custom
    assert provider.wired == [('SomeTool', {'a': 1})]


def test_auth_callback_applies_token_on_every_call():
    """``auth`` 回调每次调用都执行（adapter 借此把 key 写进 session 头）。"""
    seen = []
    post = _Post([_json_ok('ok')])
    transport = McpTransport(post, _Provider(), auth=seen.append)

    transport.call_tool('SomeTool', {}, token='key-1')
    transport.call_tool('SomeTool', {}, token='key-1')

    assert seen == ['key-1', 'key-1']
    assert post.methods.count('initialize') == 1  # 同一 token：只握手一次

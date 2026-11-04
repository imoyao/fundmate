# -*- coding: utf-8 -*-
"""MCP 传输层：会话、握手、SSE/JSON 解析、会话失效重握。

**本模块的代码是从** ``app/services/adapters/qieman_fetcher.py`` **逐字搬运的**
（2026-10-21，MCP S1）。不新写一份通用 MCP 客户端，理由写在设计文档
``docs/dev/mcp-integration.md`` §2：且慢那 6 个方法已在生产踩完四类坑 ——
事件流（SSE）响应、服务端不回 ``Mcp-Session-Id``（nginx 无状态网关，实测 2026-10-20）、
WAF 拦截返回非 JSON、会话失效后必须重握一次。重写等于把已知结论再试错一遍。

职责边界（S1 有意留空的部分，避免「没有读者的抽象」）：

- **不碰 HTTP**：``post`` 回调由调用方注入（adapter 持有 ``requests.Session`` 和鉴权头），
  换 HTTP 客户端 / 加代理不需要改这里；
- **不碰凭据来源**：``token`` 只用于「换 key 必须重新握手」的缓存键；鉴权头由 ``auth``
  回调落地（adapter 写进 ``session.headers``）。传输层既不读环境变量，也不记录 token；
- **记账在这里，不在各 adapter**（S2）：:meth:`McpTransport.call_tool` 是**所有** provider
  的唯一调用入口，故 ``mcp_call_logs`` 的写入也放在这里 —— 让每家的 adapter 各自记账，
  接第 N 家时必然有一家忘记（#171 同族：漏一处 = 该服务永远无痕）。
  ``capability`` 由调用方传入（能力名稳定，工具名会变）；不传则**不记账**，
  这样纯协议单测不会触碰数据库。

``provider`` 按**鸭子类型**使用（只读 ``protocol_version`` / ``client_info`` / ``_wire``），
本模块不 import :mod:`app.services.mcp.base`：基类要 import 本模块来构造传输，
反向 import 会成环。
"""

import hashlib
import json
import re
from typing import Any, Callable, Dict, Iterator, List, Optional

from loguru import logger

from app.services.mcp.call_log import record_call
from app.services.mcp.errors import (
    McpBadResponse,
    McpError,
    classify_exception,
    classify_http,
    classify_payload,
    sanitize,
)

#: ``post(payload, sid) -> 响应对象``。响应只需支持
#: ``status_code`` / ``headers``（dict 语义）/ ``json()`` / ``iter_lines(decode_unicode=True)``。
PostCallable = Callable[[dict, Optional[str]], Any]


class McpSessionInvalid(RuntimeError):
    """MCP 会话已失效（服务端不认当前 ``Mcp-Session-Id``）。

    仅由 :meth:`McpTransport._call_once` 抛出（400 / 404 / 返回非 JSON），
    由 :meth:`McpTransport.call_tool` 捕获后**重新握手一次**再重试；
    重试仍失败则转成普通 ``RuntimeError`` 抛出（不吞错）。
    """


def _token_fingerprint(token: str) -> str:
    """token 的摘要（会话缓存键）。

    用摘要而非原文：缓存只是为了判断「换 key 没换」，没必要把凭据多留一份在内存里。
    """
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _response_text(resp: Any) -> str:
    """响应体 → 文本，**按 UTF-8 解码**。

    ⚠️ 不能用 ``resp.text`` / ``iter_lines(decode_unicode=True)``：``text/event-stream``
    不带 ``charset``，requests 按 RFC 2616 猜成 **ISO-8859-1**，于是
    ① 中文全变乱码；② 更致命的是 UTF-8 续字节 ``0x85``（U+0085 NEXT LINE）被
    ``str.splitlines()`` 当成换行，把一行 1700 字节的 JSON **在汉字中间折断** ⇒
    ``json.loads`` 失败 ⇒ 上层读成「调用返回为空」（实测 2026-10-23，真实网关）。
    故这里一律拿原始字节自己解码。
    """
    raw = getattr(resp, 'content', None)
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw).decode('utf-8', errors='replace')
    try:
        return getattr(resp, 'text', '') or ''
    except Exception:  # noqa: BLE001 - 替身没有该成员时按「读不到」处理
        return ''


def _body_excerpt(resp: Any, limit: int = 200) -> str:
    """响应体摘要（喂给错误分类 / 采样留证）。

    取不到就返回空串 —— 分类退化为「按状态码判」，不允许因为读不到 body 就把错误吞掉。
    """
    try:
        return sanitize(_response_text(resp), limit)
    except Exception:  # noqa: BLE001 - 摘要失败不影响分类
        return ''


def _sse_payloads(body: str) -> Iterator[str]:
    """按 SSE 事件块切分，逐个产出 ``data`` 载荷。

    SSE 规范：同一事件里的多行 ``data`` 用 ``\\n`` 拼接。上游还会把超长 JSON 折行且
    **续行不带 ``data:`` 前缀**（实测 2026-10-23），故两种情况都产出候选：
    先按规范拼 ``\\n``，再按「硬折行」拼 ``''``；由调用方选能 ``json.loads`` 的那个。
    """
    blocks: List[List[str]] = []
    current: List[str] = []
    for line in re.split(r'\r\n|\r|\n', body):
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        marker = line.find('data:')
        if marker >= 0:
            chunk = line[marker + len('data:') :]
            current.append(chunk[1:] if chunk.startswith(' ') else chunk)
        elif current:
            current.append(line)
    if current:
        blocks.append(current)
    for lines in blocks:
        # ① 规范形状：同一事件的多行 data 用 \n 拼接
        yield '\n'.join(lines)
        if len(lines) > 1:
            # ② 上游硬折行（续行不带 data:）⇒ 拼接时不能插 \n
            yield ''.join(lines)
            # ③ 现实里还有「每个 data 行各自就是一条完整消息」的写法（不合规范但常见，
            #    且既有夹具与历史行为都是它）⇒ 逐行也试，谁解析得出就是谁
            yield from lines


class McpTransport:
    """一个实例服务**一个** provider（会话缓存与重试策略的唯实现）。

    会话缓存粒度 = 实例 × token 指纹：换 key 必须重新握手（服务端按 key 建会话），
    不换 key 时连续 N 次调用只握手一次。
    """

    def __init__(
        self,
        post: PostCallable,
        provider: Any,
        *,
        auth: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._post = post
        self._provider = provider
        #: provider 标识（记账与报错归属）；鸭子类型取，缺失时退回 'mcp'
        self._name = getattr(provider, 'name', '') or 'mcp'
        self._auth = auth
        #: MCP 会话（Streamable HTTP 的 ``Mcp-Session-Id``）缓存
        self._sid: Optional[str] = None
        #: 缓存会话对应的 token 指纹（换 key 必须重新握手，不能沿用旧会话）
        self._token_fp: Optional[str] = None
        #: 本实例是否已完成过一次握手。**且慢服务端不回 Mcp-Session-Id**（实测 2026-10-20，
        #: nginx 无状态网关：initialize 200 但无该响应头），此时也必须记住「已握手」，
        #: 否则「无会话可缓存」会退化成「每次调用都重新握手」，复用等于没做。
        self._handshake_done: bool = False

    # ── 公开入口 ──
    def call_tool(
        self,
        tool: str,
        arguments: dict,
        *,
        token: str,
        capability: Optional[str] = None,
        scope: Any = None,
    ) -> str:
        """调用任意 MCP 工具，返回解析出的文本片段（兼容 SSE / JSON 两种响应）。

        **会话复用**：``Mcp-Session-Id`` 缓存在实例上，正常路径下连续 N 次调用
        **只握手一次**（原实现每次调用都握手 = 3 个 HTTP 请求）。仅当服务端明确不认
        当前会话（400/404/非 JSON）时**重新握手一次**再重试同一次调用，仍失败则抛错 ——
        不做无限重试，也不把失败吞成空结果（空结果会被上层读成「这组合没持仓」）。

        Args:
            capability: 能力名（如 ``strategy_composition``）。传了才记 ``mcp_call_logs``：
                纯协议层单测不传，因此不会触碰数据库。
            scope: 数据归属（落审计表，便于回答「这次调用烧的是谁的额度」）。

        Raises:
            McpError: 失败一律类型化上抛（``McpAuthError`` / ``McpQuotaExceeded`` /
                ``McpUnavailable`` / ``McpBadResponse`` …），由 job 层决定降级与终态。
        """
        if capability is None:
            return self._call_tool_inner(tool, arguments, token=token)
        # 一次"能力调用"一行审计（含重握重试，失败同样落库），不是一次 HTTP 一行
        with record_call(self._name, capability, scope=scope):
            return self._call_tool_inner(tool, arguments, token=token)

    def _call_tool_inner(self, tool: str, arguments: dict, *, token: str) -> str:
        """``call_tool`` 的重试骨架（记账在调用方，不在这里）。

        **异常归一化（S2）**：本方法出口的异常**一律**是 :class:`McpError` 家族。
        ``_post`` 是调用方注入的回调，抛出的 ``requests.ConnectionError`` /
        ``Timeout`` / 以及任何未知异常都不经过状态码分支 —— 若原样漏出去，job 层的
        ``except McpError``（按平台隔离）就抓不到它，一个平台抖动会重新升级成整轮失败。
        在唯一入口收口，是「失败必须可分类」这条承诺的实现位置。
        """
        if self._auth is not None:
            self._auth(token)

        try:
            last_err: Optional[McpSessionInvalid] = None
            for attempt in (1, 2):
                sid = self._ensure_session(token)
                try:
                    return self._call_once(sid, tool, arguments)
                except McpSessionInvalid as e:
                    # 不论第几次，先把坏会话丢掉：下一次循环（重试）会重新握手
                    self.reset_session()
                    last_err = e
                    if attempt == 2:
                        break
                    logger.warning(f'MCP 会话失效，重新握手后重试一次（{tool}）: {e}')
            raise McpBadResponse(
                f'会话重握后仍失败（{tool}）: {last_err}',
                provider=self._name,
            ) from last_err
        except McpError:
            raise
        except Exception as e:  # noqa: BLE001 - 网络/未知异常统一分类（失败不得以裸异常形态漏出）
            raise classify_exception(e, provider=self._name) from e

    def reset_session(self) -> None:
        """丢弃缓存会话（下次 :meth:`_ensure_session` 会重新握手）。"""
        self._sid = None
        self._token_fp = None
        self._handshake_done = False

    # ── 会话 ──
    def _ensure_session(self, token: str) -> Optional[str]:
        """取/建 MCP 会话：实例内缓存 sid，token 变了才重新握手。

        **服务端不回 ``Mcp-Session-Id`` 时同样跳过后续握手**（实测 2026-10-20）：
        且慢网关是无状态的，initialize 只回 200、无该响应头，且不带任何会话头直接
        ``tools/call`` 依然 200 有数据 ⇒ 「无 sid」不等于「无会话」。
        若上游日后真要求先握手，退路是 :meth:`call_tool` 的会话失效分支 ——
        失败即重握一次再重试（已在真实链路上验证过重试路径，见测试）。
        """
        fp = _token_fingerprint(token)
        if self._token_fp == fp and (self._sid or self._handshake_done):
            return self._sid

        sid = self._handshake()
        r = self._post({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, sid)
        if r.status_code >= 400:
            raise classify_http(r.status_code, _body_excerpt(r), provider=self._name)
        sid = r.headers.get('Mcp-Session-Id') or sid
        self._sid = sid
        self._token_fp = fp
        self._handshake_done = True
        return sid

    def _handshake(self) -> Optional[str]:
        """MCP 握手（initialize），返回会话 sid。

        注意（实测 2026-10-20）：且慢当前**不返回** ``Mcp-Session-Id``，此方法返回 None
        也属正常；会话复用由 :meth:`_ensure_session` 的 ``_handshake_done`` 记位承担。
        """
        r = self._post(
            {
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'initialize',
                'params': {
                    'protocolVersion': self._provider.protocol_version,
                    'capabilities': {},
                    'clientInfo': self._provider.client_info,
                },
            },
            None,
        )
        if r.status_code != 200:
            raise classify_http(r.status_code, _body_excerpt(r), provider=self._name)
        return r.headers.get('Mcp-Session-Id')

    # ── 调用 ──
    def _call_once(self, sid: Optional[str], tool: str, arguments: dict) -> str:
        """在既有会话内发一次 ``tools/call``；会话失效抛 :class:`McpSessionInvalid`。"""
        r3 = self._post(self._provider._wire(tool, arguments), sid)
        if r3.status_code in (400, 404):
            # 400 有**两种**语义，实测（2026-10-23，某家网关）：
            #   ① 请求体不符合 JSON-RPC ⇒ 上游回 {"error": {"code": -32602, "message": "Validation error…"}}；
            #   ② 会话失效 / WAF 拦截 ⇒ 非 JSON 或与协议无关的报文。
            # 旧实现把 400 一律当 ②，于是「重握 → 再 400 → 包成『会话重握后仍失败』」，
            # **响应体被丢弃**：本可一眼看出的校验错变成了一句瞎猜（#2516 采样时实测）。
            # 故：能解析出 JSON-RPC error 就按 payload 分类（重握手没有意义）；否则才算会话失效，
            # 且**报文必须带进错误里**（探针的 --save-body 就是靠它留证）。
            payload_error = self._payload_error(r3)
            if payload_error is not None:
                raise classify_payload(payload_error, provider=self._name)
            raise McpSessionInvalid(f'HTTP {r3.status_code}: {_body_excerpt(r3, 400)}')
        if r3.status_code != 200:
            # 401/403 → 授权失效；429 → 频控/额度；5xx → 服务不可用。全部类型化上抛，
            # 让 job 层能区分「该换 Token」与「等一会儿再试」。
            raise classify_http(r3.status_code, _body_excerpt(r3), provider=self._name)

        content_type = (r3.headers.get('content-type') or '').lower()
        if 'text/event-stream' in content_type:
            text = self._text_from_sse(r3)
        else:
            try:
                msg = r3.json()
            except ValueError:
                # 非 JSON：会话失效或被 WAF 拦截。两者都值得先重握一次再判死（不吞错）。
                raise McpSessionInvalid('返回非 JSON（疑似会话失效或被 WAF 拦截）') from None
            if 'error' in msg:
                raise classify_payload(msg['error'], provider=self._name)
            text = self._text_from_result(msg.get('result', {}))
        if not text:
            raise McpBadResponse('调用返回为空', provider=self._name)
        return text

    @staticmethod
    def _payload_error(resp: Any) -> Optional[Any]:
        """响应体里的 JSON-RPC ``error`` 字段（取不到返回 ``None``）。

        只用于 4xx 的**语义区分**：能拿到结构化 error 就是「请求/参数错」，
        拿不到（HTML、空体、非 JSON）才按会话失效处理。
        """
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001 - 非 JSON / 替身没有 json() 都算「拿不到」
            return None
        if isinstance(body, dict) and body.get('error'):
            return body['error']
        return None

    def _text_from_sse(self, resp: Any) -> str:
        """从事件流里取 ``id == 2``（tools/call）那条消息的文本片段。

        两个实测坑（2026-10-23，真实网关），都由 :func:`_response_text` /
        :func:`_sse_payloads` 兜住：

        1. **不能用 ``iter_lines(decode_unicode=True)``**：``text/event-stream`` 无 charset
           ⇒ requests 按 ISO-8859-1 解码 ⇒ UTF-8 续字节 ``0x85`` 被当成换行，
           一行 JSON 在汉字中间被折断，``json.loads`` 全部失败 ⇒ 报「调用返回为空」；
        2. ``event:`` 与 ``data:`` 可能在同一行，也可能分成两行；超长 JSON 还可能硬折行。
        """
        for payload in _sse_payloads(_response_text(resp)):
            try:
                msg = json.loads(payload)
            except ValueError:
                continue
            if msg.get('id') == 2 and 'result' in msg:
                return self._text_from_result(msg['result'])
        return ''

    def _text_from_result(self, result: Dict[str, Any]) -> str:
        """``result`` → 文本片段；``isError`` 为真时抛类型化错误。

        为什么必须查 ``isError``（实测 2026-10-23，某家网关）：工具名写错时上游回的是
        **HTTP 200** + ``{"isError": true, "content": [{"text": "工具不存在: …"}]}``。
        只看状态码会把这段错误文本当数据返回，随后在解析层报「结构异常」——
        报错方向指向解析，而真因是工具名（#171 同族：失败被读成「没有数据」）。
        """
        if result.get('isError'):
            raise McpBadResponse(self._error_message(result), provider=self._name)
        content = result.get('content', [])
        return ''.join(c.get('text', '') for c in content if c.get('type') == 'text')

    @staticmethod
    def _error_message(result: Dict[str, Any]) -> str:
        """``isError`` 的错误文案：优先 ``structuredContent.message``，否则拼 content 文本。"""
        structured = result.get('structuredContent')
        if isinstance(structured, dict) and structured.get('message'):
            return str(structured['message'])
        text = ''.join(c.get('text', '') for c in result.get('content') or [] if c.get('type') == 'text')
        return text or 'isError=true 但上游未给错误文案'

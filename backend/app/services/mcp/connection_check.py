# -*- coding: utf-8 -*-
"""连接校验（S5f）：拿用户凭据向上游握手 + 拉工具清单，回答「连上之后能干什么」。

凭据存进表里只是状态，**能调通上游并报出它的工具清单**才是连接的价值：
- 授权过期 / Key 失效在用户点校验的那一刻暴露成明确文案，而不是等业务调用时炸；
- 工具清单直接展示给用户 —— 上游有什么能力（账户 / 持仓 / 流水…）一目了然，
  也是后续能力登记（``providers/*.py`` 的 ``_CAPABILITY_TOOLS``）的采样入口。

握手 / 会话复用 / 失效重握的唯一实现在 :class:`McpTransport`（本模块**不复刻**），
这里只通过它的两个内部钩子取会话与发请求 —— 同包内受控复用，绕开会把基线顶破的
公开 API 扩面；解析层（SSE / JSON-RPC error）用最简实现，校验场景容忍窄覆盖。
"""

import json
from typing import Any, Dict, List, Optional

import requests

from app.core.constants import DEFAULT_REQUEST_TIMEOUT, USER_AGENT
from app.services.mcp.credentials import DataScope, resolve_token
from app.services.mcp.errors import McpBadResponse, classify_http, classify_payload
from app.services.mcp.registry import get_provider
from app.services.mcp.transport import McpTransport

#: 校验用的能力名：不在任何 provider 的映射里，``scope_of`` 落基类默认 ``USER_PRIVATE``
#: ⇒ ``resolve_token`` 走用户分支 —— 校验的语义就是「**用户自己的**凭据能不能调通」。
_CHECK_CAPABILITY = 'connection_check'


def _post_factory(provider: Any, token: str):
    """构造传输层的 ``post`` 回调（HTTP 细节；与 wind 系适配器同形状）。"""
    session = requests.Session()

    def post(payload: dict, sid: Optional[str]) -> requests.Response:
        headers: Dict[str, str] = {
            **provider.auth_headers(token),
            'Accept': 'application/json, text/event-stream',
            'Content-Type': 'application/json',
            'User-Agent': USER_AGENT,
        }
        if sid:
            headers['Mcp-Session-Id'] = sid
        return session.post(provider.base_url(), json=payload, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT)

    return post


def _tools_from_response(resp: requests.Response, provider_name: str) -> List[Dict[str, Any]]:
    """``tools/list`` 响应 → 工具数组；HTTP / 协议错误按既有分类上抛。"""
    if resp.status_code != 200:
        raise classify_http(resp.status_code, resp.text[:200], provider=provider_name)
    msg: Dict[str, Any]
    if 'text/event-stream' in (resp.headers.get('content-type') or '').lower():
        # SSE：取最后一个能解析的 data 块（tools/list 只有一帧结果）
        for block in reversed(resp.text.split('\n\n')):
            for line in block.splitlines():
                if line.startswith('data:'):
                    try:
                        msg = json.loads(line[len('data:') :].strip())
                    except ValueError:
                        continue
                    break
            else:
                continue
            break
        else:
            raise McpBadResponse('上游工具清单响应不是可解析的 SSE 帧', provider=provider_name)
    else:
        try:
            msg = resp.json()
        except ValueError:
            raise McpBadResponse('上游工具清单响应不是 JSON', provider=provider_name) from None
    if 'error' in msg:
        raise classify_payload(msg['error'], provider=provider_name)
    tools = msg.get('result', {}).get('tools')
    if not isinstance(tools, list):
        raise McpBadResponse('上游工具清单缺少 tools 字段', provider=provider_name)
    return tools


def check_connection(provider: str, user_id: Any) -> Dict[str, Any]:
    """校验用户的 provider 连接：握手 → ``tools/list`` → 归一化工具清单。

    Raises:
        McpUserTokenMissing: 用户尚未连接（视图层转 422）。
        McpAuthError: 凭据过期 / 上游拒绝（视图层转 502，文案可直接展示）。
        McpError: 其余上游与协议错误（均已脱敏，``user_message`` 可直接展示）。
    """
    provider_obj = get_provider(provider)
    token = resolve_token(provider, DataScope.USER_PRIVATE, user_id=user_id)
    transport: McpTransport = provider_obj.build_transport(_post_factory(provider_obj, token))
    # 同包受控复用（见模块 docstring）：握手与请求都走传输层的既有实现
    sid = transport._ensure_session(token)
    resp = transport._post({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'}, sid)
    tools = _tools_from_response(resp, provider_obj.name)
    normalized = [
        {
            'name': str(tool.get('name') or ''),
            'description': str(tool.get('description') or ''),
        }
        for tool in tools
        if tool.get('name')
    ]
    return {
        'provider': provider,
        'tool_count': len(normalized),
        'tools': normalized,
    }

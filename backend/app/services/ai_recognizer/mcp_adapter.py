# -*- coding: utf-8 -*-
"""MCP 协议适配层（#1751 S5）：同一份 TOOLS_METADATA 的第二套协议外衣。

本层就是「schema 单一真相源」的直接证明——元数据一个字不改，只做两次映射：

- list_tools：TOOLS_METADATA → types.Tool（parameters 原样透传为 input_schema）；
- call_tool ：ToolExecutor.run（P1 覆盖 → schema 校验 → 派发，与 FC 循环同一把刀）
              → types.CallToolResult（success → JSON 文本 + structured_content；error → is_error）。

与对话循环（agent_loop）的边界：护栏（B 规则 / G6 路由）、轮次闸、配额是
**HTTP 对话协议**的闸门——MCP 客户端（Cursor / Claude Desktop）自带模型宿主，
本层的安全边界是「工具只读 + server_ctx 权威覆盖」（stdio = 本机进程，
family_id 只由服务端环境变量决定，见 mcp_server._server_ctx）。
"""

import json
from typing import Any, List, Optional

from mcp import types

from app.services.ai_recognizer.tools import TOOLS_METADATA, ToolExecutor


def iter_mcp_tools() -> List[types.Tool]:
    """TOOLS_METADATA → MCP 工具清单（name / description / input_schema 保真透传）。"""
    return [
        types.Tool(name=meta['name'], description=meta['description'], input_schema=meta['parameters'])
        for meta in TOOLS_METADATA
    ]


def execute_tool(name: str, arguments: Optional[dict], server_ctx: Optional[dict]) -> types.CallToolResult:
    """执行一次 MCP 工具调用，把 ToolExecutor 的 {status, data|msg} 信封映射为 CallToolResult。

    - success：content 为 JSON 文本（所有客户端可读），structured_content 为原始结构
      （支持结构化输出的客户端可直接消费）；
    - error：is_error=true + msg 入 content——与 FC 路径的 error-as-observation 同哲学：
      失败是给调用方看的观测值，不是进程级异常。
    """
    result = ToolExecutor.run(name, arguments or {}, server_ctx)
    if result.get('status') == 'success':
        data: Any = result.get('data')
        return types.CallToolResult(
            content=[types.TextContent(type='text', text=json.dumps(data, ensure_ascii=False, default=str))],
            structured_content=data,
            is_error=False,
        )
    return types.CallToolResult(
        content=[types.TextContent(type='text', text=str(result.get('msg') or '工具执行失败'))],
        is_error=True,
    )


__all__ = ['execute_tool', 'iter_mcp_tools']

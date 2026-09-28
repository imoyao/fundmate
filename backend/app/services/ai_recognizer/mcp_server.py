# -*- coding: utf-8 -*-
"""账本精灵 MCP server（stdio 传输，#1751 S5）。

启动（backend 目录下）：

    pdm run agent-mcp        # = python -m app.services.ai_recognizer.mcp_server

MCP 客户端（Cursor / Claude Desktop）配置样例见
``docs/working-notes/agent-dev-progress-2026-09-26.md`` 步骤卡 #9。

设计要点：

- 低层 ``Server`` + 构造器回调（mcp 2.0.0 已移除装饰器与内置 FastMCP），
  ``on_list_tools`` / ``on_call_tool`` 直连适配层，中间零业务逻辑；
- family_id 只由环境变量 ``FUNDMATE_MCP_FAMILY_ID`` 决定（缺省 1，与
  ``core.auth.get_family_id`` 单用户口径一致）——客户端传什么都会被
  ``apply_server_context`` 覆盖，P1 在 MCP 路径同样成立；
- 启动时 ``chdir`` 锚回 backend：默认库路径 ``sqlite:///./invest.db`` 相对 cwd，
  而 stdio server 由客户端以**任意 cwd** 拉起，不锚回会连到「另一个空库」（数据隐身）。
"""

import os
from pathlib import Path

import anyio
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from app.services.ai_recognizer.mcp_adapter import execute_tool, iter_mcp_tools

SERVER_NAME = 'fundmate-agent'
SERVER_VERSION = '0.1.0'
# mcp_server.py -> ai_recognizer -> services -> app -> backend
BACKEND_DIR = Path(__file__).resolve().parents[3]


def _server_ctx() -> dict:
    """服务端权威上下文：family_id 仅由本机环境变量决定（客户端不可指定）。"""
    try:
        family_id = int(os.environ.get('FUNDMATE_MCP_FAMILY_ID') or 1)
    except ValueError:
        family_id = 1
    return {'family_id': family_id}


async def on_list_tools(_ctx: object, _params: object) -> types.ListToolsResult:
    """tools/list：schema 单一真相源直出，不缓存不裁剪。"""
    return types.ListToolsResult(tools=iter_mcp_tools())


async def on_call_tool(_ctx: object, params: types.CallToolRequestParams) -> types.CallToolResult:
    """tools/call：透传适配层（ToolExecutor 内完成 P1 覆盖与 schema 校验）。"""
    return execute_tool(params.name, params.arguments, _server_ctx())


def build_server() -> Server:
    """组装低层 Server（纯组装，无 I/O——便于单测直接调用回调）。"""
    return Server(
        SERVER_NAME,
        version=SERVER_VERSION,
        description='多多贝账本精灵只读工具（与内置 Agent 循环同一份 TOOLS_METADATA）',
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


async def _serve() -> None:
    server = build_server()
    init_options = server.create_initialization_options()
    async with stdio_server() as (read, write):
        await server.run(read, write, init_options)


def main() -> None:
    """进程入口：锚回 backend（默认库相对 cwd）后进入 stdio 服务循环。"""
    os.chdir(BACKEND_DIR)
    anyio.run(_serve)


if __name__ == '__main__':
    main()

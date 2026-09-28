# -*- coding: utf-8 -*-
"""MCP 协议层测试（#1751 S5）。

三层判据：
1. schema 保真——MCP 工具清单与 TOOLS_METADATA 逐一相等（「同一份 schema 双协议暴露」的字面判据）；
2. 调用路由——成功 / 未知工具 / 缺参 / server_ctx 透传（P1）在 MCP 路径上的行为；
3. stdio 握手冒烟——子进程真起 server，initialize → list_tools → call_tool 走真实 JSON-RPC。
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.services.ai_recognizer import mcp_adapter, mcp_server
from app.services.ai_recognizer.tools import TOOLS_METADATA

BACKEND_DIR = Path(__file__).resolve().parents[3]


# ── 1. schema 保真（双协议同源的判据） ──────────────────────────────────────
def test_iter_mcp_tools_schema_identical_to_tools_metadata():
    tools = mcp_adapter.iter_mcp_tools()
    assert len(tools) == len(TOOLS_METADATA)
    for mcp_tool, meta in zip(tools, TOOLS_METADATA):
        assert mcp_tool.name == meta['name']
        assert mcp_tool.description == meta['description']
        assert mcp_tool.input_schema == meta['parameters']


def test_on_list_tools_handler_wraps_result():
    result = asyncio.run(mcp_server.on_list_tools(None, None))
    assert isinstance(result, types.ListToolsResult)
    assert [t.name for t in result.tools] == [m['name'] for m in TOOLS_METADATA]


# ── 2. 调用路由（经 ToolExecutor，与 FC 路径同一把刀） ──────────────────────
def test_execute_tool_success_roundtrip():
    result = mcp_adapter.execute_tool('get_fund_nav', {'fund_codes': ['000000']}, None)
    assert result.is_error is False
    payload = json.loads(result.content[0].text)
    assert 'navs' in payload
    assert result.structured_content == payload


def test_on_call_tool_handler_roundtrip():
    params = types.CallToolRequestParams(name='get_fund_nav', arguments={'fund_codes': ['000000']})
    result = asyncio.run(mcp_server.on_call_tool(None, params))
    assert result.is_error is False


def test_execute_tool_unknown_tool_is_error():
    result = mcp_adapter.execute_tool('not_a_tool', {}, None)
    assert result.is_error is True
    assert '未知工具' in result.content[0].text


def test_execute_tool_missing_required_is_error():
    result = mcp_adapter.execute_tool('get_fund_nav', {}, None)
    assert result.is_error is True
    assert '缺少必填参数' in result.content[0].text


def test_execute_tool_passes_server_ctx_to_executor(monkeypatch):
    """适配层必须把 server_ctx 原样交给 ToolExecutor（P1 的前提）。"""
    captured = {}

    class _FakeExecutor:
        @staticmethod
        def run(name, params, server_ctx=None):
            captured.update(name=name, params=params, server_ctx=server_ctx)
            return {'status': 'success', 'data': {}}

    monkeypatch.setattr(mcp_adapter, 'ToolExecutor', _FakeExecutor)
    result = mcp_adapter.execute_tool('get_assets_overview', {'family_id': 999}, {'family_id': 1})
    assert result.is_error is False
    assert captured['server_ctx'] == {'family_id': 1}
    assert captured['params'] == {'family_id': 999}


def test_client_family_id_overridden_by_server_ctx(db, make_position):
    """P1 判据：客户端传真 family_id=999 也拿不到 family 1 之外的数据（权威值覆盖）。"""
    make_position(
        symbol='110011',
        name='本人持仓',
        family_id=1,
        quantity=100,
        avg_price=1.0,
        current_price=2.0,
    )
    result = mcp_adapter.execute_tool(
        'list_position_pnl',
        {'family_id': 999},
        {'family_id': 1},
    )
    assert result.is_error is False, result.content[0].text
    assert result.structured_content['count'] >= 1  # 若覆盖失败（用了 999）则为 0


# ── 3. server_ctx 来源（family_id 只由本机 env 决定） ───────────────────────
def test_server_ctx_family_id_from_env(monkeypatch):
    monkeypatch.setenv('FUNDMATE_MCP_FAMILY_ID', '7')
    assert mcp_server._server_ctx() == {'family_id': 7}
    monkeypatch.setenv('FUNDMATE_MCP_FAMILY_ID', 'junk')
    assert mcp_server._server_ctx() == {'family_id': 1}
    monkeypatch.delenv('FUNDMATE_MCP_FAMILY_ID')
    assert mcp_server._server_ctx() == {'family_id': 1}


def test_build_server_declares_tools_capability():
    server = mcp_server.build_server()
    init_options = server.create_initialization_options()
    assert init_options.server_name == mcp_server.SERVER_NAME
    assert init_options.capabilities.tools is not None


# ── 4. stdio 握手冒烟（子进程真起 server，真实 JSON-RPC 往返） ───────────────
def test_stdio_handshake_lists_and_calls_tools(tmp_path):
    """验收③：initialize → list_tools（6 个）→ call_tool 真跑一条。"""
    env = os.environ.copy()
    env.update(
        {
            'APP_ENV': 'development',
            'DEV_DATABASE_URL': 'sqlite:///' + (tmp_path / 'market.db').as_posix(),
            'DEV_USER_DATABASE_URL': 'sqlite:///' + (tmp_path / 'user.db').as_posix(),
            # 空串即 falsy，防本地 .env 把子进程指到真 Supabase / Turso
            'SUPABASE_DATABASE_URL': '',
            'TURSO_DATABASE_URL': '',
            'PYTHONUTF8': '1',
            'PYTHONPATH': str(BACKEND_DIR),
        }
    )
    child = BACKEND_DIR / 'tests' / 'services' / 'ai_recognizer' / 'mcp_smoke_child.py'

    async def _roundtrip():
        params = StdioServerParameters(command=sys.executable, args=[str(child)], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=90) as session:
                init = await session.initialize()
                tools = await session.list_tools()
                call = await session.call_tool('get_fund_nav', {'fund_codes': ['000000']})
                return init, tools, call

    init, tools, call = asyncio.run(_roundtrip())
    assert init.capabilities.tools is not None
    assert [t.name for t in tools.tools] == [m['name'] for m in TOOLS_METADATA]
    assert call.is_error is False, call.content
    payload = json.loads(call.content[0].text)
    assert 'navs' in payload

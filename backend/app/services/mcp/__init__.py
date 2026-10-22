# -*- coding: utf-8 -*-
"""MCP 接入层（S1：传输 + provider 基类 + 注册表）。

目录职责见 ``docs/dev/mcp-integration.md`` §4.1：

- :mod:`app.services.mcp.transport` —— 会话 / 握手 / SSE 解析 / 失效重握（唯一实现）；
- :mod:`app.services.mcp.base` —— ``McpProvider`` 模板方法（子类只填钩子）；
- :mod:`app.services.mcp.registry` —— ``name → provider`` 注册表（Ports & Adapters）；
- :mod:`app.services.mcp.providers` —— 每服务一个子类（S1 只有且慢，Wind 在 S3）。

本层是 **services 共享件**：可以被家族包与 ``adapters`` 依赖，但**不得**反向依赖它们
（判据：``scripts/guard_layer_direction.py`` 的 R7）。
"""

from app.services.mcp.base import McpProvider
from app.services.mcp.registry import UnknownMcpProvider, get_provider, provider_names, register_provider
from app.services.mcp.transport import McpSessionInvalid, McpTransport

__all__ = [
    'McpProvider',
    'McpSessionInvalid',
    'McpTransport',
    'UnknownMcpProvider',
    'get_provider',
    'provider_names',
    'register_provider',
]

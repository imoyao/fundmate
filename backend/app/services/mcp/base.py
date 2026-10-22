# -*- coding: utf-8 -*-
"""MCP provider 基类（模板方法）。

设计意图见 ``docs/dev/mcp-integration.md`` §4.2：**流程唯一实现、子类只填钩子**。
每家服务各写一遍「会话复用 + 失效重握 + 错误分类」必然漂移，故流程落在
:class:`app.services.mcp.transport.McpTransport`，本类只描述「这家服务长什么样」：

============================  ==========================================
钩子                          读者
============================  ==========================================
``base_url()``                适配器组请求地址（含 §8 的本地 mock 覆盖点）
``auth_headers(token)``       适配器组鉴权 / 来源头
``tool_for(capability)``      业务方法取工具名（静态映射，§6.3 不做自然语言检索）
``_wire(tool, arguments)``    传输层组 ``tools/call`` 请求体（S3 的 Wind 覆盖它）
============================  ==========================================

S1 **有意不做**的事（不是遗漏，是没有读者）：

- ``data_scope()`` / 凭据路由：S2 已补 —— ``scope_of()`` 默认 **``USER_PRIVATE``**
  （归属未知时保守，§5.1），由 :mod:`app.services.mcp.credentials` 消费；
- 采集 / 记账 / 缓存：``mcp_call_logs`` 与 ``/api/health`` 已在 S2 接入（记账在
  :class:`~app.services.mcp.transport.McpTransport` 的唯一入口，不在各 adapter）；
- ``extract()``（表格 → canonical）：S3 只有 Wind 需要，且慢这边就是 ``json``。

判定抽象是否成立的三条见设计文档 §10；任何一步都可以独立合并 / 回滚。
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional

from app.services.mcp.credentials import DataScope
from app.services.mcp.transport import McpTransport, PostCallable


class McpProvider(ABC):
    """一家 MCP 服务（注册表以 :attr:`name` 为键）。"""

    #: 注册表键，同时用于日志与账单归属
    name: str = ''
    #: 握手协议版本（各家可能不同，故是实例属性而非模块常量）
    protocol_version: str = '2024-11-05'
    #: 握手时上报的客户端信息（服务端用于统计，不含任何凭据）
    client_info: Dict[str, str] = {'name': 'fundmate', 'version': '1.0.0'}

    @abstractmethod
    def base_url(self) -> str:
        """服务地址。"""

    @abstractmethod
    def auth_headers(self, token: str) -> Dict[str, str]:
        """鉴权与来源头。

        约定：**空 token 时不得伪造占位值** —— 宁可少一个头让服务端明确拒绝，
        也不要发一个假 key 把「没配凭据」伪装成「凭据错误」。
        """

    @abstractmethod
    def tool_for(self, capability: str) -> str:
        """能力名 → 工具名（静态映射）。未知能力应抛 ``KeyError``，不猜。"""

    def scope_of(self, capability: str) -> DataScope:
        """该能力的数据归属（决定用系统 Token 还是用户 Token）。

        **默认 ``USER_PRIVATE``**：新接一家服务时，判不清归属就按用户私有处理 ——
        宁可少一个功能，也不许误用系统额度（§5.1）。公开能力必须在子类里显式覆盖。
        """
        return DataScope.USER_PRIVATE

    def _wire(self, tool: str, arguments: dict) -> Dict[str, Any]:
        """``tools/call`` 请求体（JSON-RPC 2.0 默认形状）。

        扩展点：Wind 网关的请求形状与标准 JSON-RPC 不同（S3 实测后覆盖本方法），
        这样接一家新服务不需要改 ``transport.py``。
        """
        return {
            'jsonrpc': '2.0',
            'id': 2,
            'method': 'tools/call',
            'params': {'name': tool, 'arguments': arguments},
        }

    def build_transport(
        self,
        post: PostCallable,
        *,
        auth: Optional[Callable[[str], None]] = None,
    ) -> McpTransport:
        """为某条 HTTP 通道构造传输（``post`` / ``auth`` 由持有连接的适配器提供）。"""
        return McpTransport(post, self, auth=auth)

# -*- coding: utf-8 -*-
"""同花顺投资账本（tzzb）MCP provider：服务地址与鉴权形状。

OAuth 授权编排（DCR / 回调 / 续期）在 ``app/services/mcp/oauth.py``；本模块只描述
「这家服务长什么样」。数据全部是用户私有（账户 / 持仓 / 盈亏 / 流水），保持基类默认
``USER_PRIVATE`` —— 取不到用户凭据就响亮地抛 ``McpUserTokenMissing``，绝不回退系统 Token。

工具名登记纪律：**没有真机采过样的工具名不进映射**（§6.3 不做自然语言检索、不猜工具名）。
上游实测提供 15 个只读工具（账户发现 / 持仓 / 盈亏 / 流水），具体名字待采样后逐个登记；
在那之前 ``tool_for`` 对一切能力抛 ``KeyError``，调用侧唯一可用路径是连接校验（tools/list）。
"""

import os
from typing import Dict

from app.services.mcp.base import McpProvider
from app.services.mcp.registry import register_provider

#: 默认服务地址；``TZZB_MCP_URL`` 可覆盖（§8 的本地 mock 切换点）
TZZB_MCP_URL = 'https://tzzb.10jqka.com.cn/mcp'
#: 握手协议版本（Streamable HTTP）
TZZB_PROTOCOL_VERSION = '2024-11-05'
#: 握手时上报的客户端信息（不含任何凭据）；client_name 会展示给上游与授权页
TZZB_CLIENT_INFO = {'name': '多多贝投资账本', 'version': '1.0.0'}

#: 能力名 → 工具名（真机采样后逐个登记；现状为空 ⇒ ``tool_for`` 一律拒绝）
_CAPABILITY_TOOLS: Dict[str, str] = {}


@register_provider
class TzzbProvider(McpProvider):
    """同花顺投资账本 MCP：用户账户 / 持仓 / 盈亏 / 流水（只读）。"""

    name = 'tzzb'
    protocol_version = TZZB_PROTOCOL_VERSION
    client_info = TZZB_CLIENT_INFO

    def base_url(self) -> str:
        return os.getenv('TZZB_MCP_URL') or TZZB_MCP_URL

    def auth_headers(self, token: str) -> Dict[str, str]:
        # 空 token 时不伪造占位值（基类红线）：宁可让服务端明确拒绝
        if not token:
            return {}
        return {'Authorization': f'Bearer {token}'}

    def tool_for(self, capability: str) -> str:
        try:
            return _CAPABILITY_TOOLS[capability]
        except KeyError:
            raise KeyError('同花顺投资账本的工具名尚未采样登记，暂不支持直接调用工具') from None

# -*- coding: utf-8 -*-
"""且慢（盈米）MCP provider：服务地址、协议常量、工具名映射。

常量从 ``app/services/adapters/qieman_fetcher.py`` 搬到这里（2026-10-21，MCP S1）：
协议与工具名属于「这家服务长什么样」，不是业务取数逻辑。搬运后
``qieman_fetcher`` 仍然再导出同样几个名字，故既有导入点（含测试）不必改 ——
``adapters → mcp`` 是合法方向，``mcp → adapters`` 由守卫 R7 拦截。

数据面归属：且慢的组合持仓 / 概览都是**平台公开**数据（用户只需一个平台 key，
不涉及账户私有数据），凭据路由在 S2 实现，届时本类补 ``data_scope()``。
"""

import os
from typing import Dict

from app.services.mcp.base import McpProvider
from app.services.mcp.registry import register_provider

#: 默认服务地址；``QIEMAN_MCP_URL`` 可覆盖（设计文档 §8 的「本地 mock / 一键切换」预留点，
#: 用环境变量而非库表，避免为了测试把地址写成可被用户改的配置）
QIEMAN_MCP_URL = 'https://stargate.yingmi.com/mcp/v2'
#: 握手协议版本（Streamable HTTP）
QIEMAN_PROTOCOL_VERSION = '2024-11-05'
#: 握手时上报的客户端信息（不含凭据）
QIEMAN_CLIENT_INFO = {'name': 'fundmate', 'version': '1.0.0'}
#: 工具名（静态映射，生产链路不做自然语言检索，见设计文档 §6.3）
QIEMAN_TOOL = 'GetLatestQuotations'  # 市场温度计
QIEMAN_STRATEGY_DETAIL_TOOL = 'GetStrategyDetails'  # 投顾组合概览/风险收益指标
QIEMAN_STRATEGY_COMPOSITION_TOOL = 'BatchGetStrategiesComposition'  # 投顾组合持仓

#: 能力名 → 工具名（能力名是业务侧的稳定词，工具名可能随上游变化）
_CAPABILITY_TOOLS: Dict[str, str] = {
    'latest_quotations': QIEMAN_TOOL,
    'strategy_details': QIEMAN_STRATEGY_DETAIL_TOOL,
    'strategy_composition': QIEMAN_STRATEGY_COMPOSITION_TOOL,
}


@register_provider
class QiemanProvider(McpProvider):
    """且慢 MCP：市场温度 + 投顾组合持仓 / 概览。"""

    name = 'qieman'
    protocol_version = QIEMAN_PROTOCOL_VERSION
    client_info = QIEMAN_CLIENT_INFO

    def base_url(self) -> str:
        return os.getenv('QIEMAN_MCP_URL') or QIEMAN_MCP_URL

    def auth_headers(self, token: str) -> Dict[str, str]:
        base = self.base_url()
        headers = {
            # 且慢网关按 Origin/Referer 判来源（缺了会被 WAF 拦成非 JSON，见 transport 注释）
            'Origin': base,
            'Referer': base + '/',
        }
        if token:
            headers['x-api-key'] = token
        return headers

    def tool_for(self, capability: str) -> str:
        try:
            return _CAPABILITY_TOOLS[capability]
        except KeyError:
            raise KeyError(f'且慢没有能力 {capability}（已知：{", ".join(sorted(_CAPABILITY_TOOLS))}）') from None

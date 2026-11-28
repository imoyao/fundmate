# -*- coding: utf-8 -*-
"""同花顺投资账本（tzzb）MCP provider：服务地址与鉴权形状。

OAuth 授权编排（DCR / 回调 / 续期）在 ``app/services/mcp/oauth.py``；本模块只描述
「这家服务长什么样」。数据全部是用户私有（账户 / 持仓 / 盈亏 / 流水），保持基类默认
``USER_PRIVATE`` —— 取不到用户凭据就响亮地抛 ``McpUserTokenMissing``，绝不回退系统 Token。

工具名登记纪律：**没有真机采过样的工具名不进映射**（§6.3 不做自然语言检索、不猜工具名）。
上游实测提供 15 个只读工具（账户发现 / 持仓 / 盈亏 / 流水）：2026-11-28 真机 verify 与
全链路 tools/list 已采到全部 15 个名字并登记进 ``TOOL_CAPABILITIES``（能力标注，S5g）；
业务调用的 ``_CAPABILITY_TOOLS``
仍在待业务接入时逐个登记 —— 在那之前 ``tool_for`` 对一切能力抛 ``KeyError``，
调用侧唯一可用路径是连接校验（tools/list）、工具目录（mcp_provider_tools）与
数据同步流（``sync_flow.py``，自带工具白名单）。
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

#: 能力名 → 工具名（真机采样后逐个登记；其余能力待采样 ⇒ ``tool_for`` 一律拒绝）
_CAPABILITY_TOOLS: Dict[str, str] = {}

#: 工具名 → Fund Mate 内部能力标签（S5g 能力高亮）。
#: 15 个名字全部来自 2026-11-28 真机连接 verify + 全链路 tools/list 的上游清单
#: （17:20 用户授权窗口实测），无猜测登记。对账候选：``queryAssetChangeSummary``
#: （资产变动汇总，与内部流水逐笔核对的第一工具）。
TOOL_CAPABILITIES: Dict[str, str] = {
    'promptAccountSelection': '账户管理',
    'queryFundAccount': '账户管理',
    'queryStockPosition': '持仓对账',
    'queryClearedPosition': '清仓周期',
    'queryFundHoldingReturns': '收益分析',
    'queryPnlSummary': '盈亏分析',
    'queryDayProfitSummary': '每日收益',
    'queryDayCalendarSummary': '收益日历',
    'queryMonthCalendarSummary': '收益日历',
    'queryMoneyHistory': '交易对账',
    'queryFundSummaryHistory': '交易对账',
    'queryAssetChangeSummary': '交易对账',
    'queryFundFeeRate': '行情辅助',
    'queryFundConfirmNav': '行情辅助',
    'queryStockMarketRemark': '行情辅助',
}


@register_provider
class TzzbProvider(McpProvider):
    """同花顺投资账本 MCP：用户账户 / 持仓 / 盈亏 / 流水（只读）。"""

    name = 'tzzb'
    protocol_version = TZZB_PROTOCOL_VERSION
    client_info = TZZB_CLIENT_INFO
    tool_capabilities = TOOL_CAPABILITIES

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

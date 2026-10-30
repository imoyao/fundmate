# -*- coding: utf-8 -*-
"""Wind **股票数据** vserver 的 provider（S5 / #2749）。

## 为什么不是复用 ``WindProvider`` 的名字

万得把数据按 vserver 分域部署，**两个域的协议形状不同**（2026-10-30 真机实测）：

=============================================  ==========================================
``/vserver_index_data`` / ``/vserver_economic_data``  ``/vserver_stock_data``
=============================================  ==========================================
上游只暴露两个工具：``market_search_tools`` /   上游**直接**暴露 10 个数据工具
``market_call_tool``，数据查询必须经后者转发        （``get_stock_basicinfo`` / ``get_stock_kline`` …）
→ :class:`~app.services.mcp.providers.wind.WindProvider` 的 ``_wire`` 正是这套  → 必须走标准 ``tools/call``，
                                                **没有** ``market_call_tool``
=============================================  ==========================================

把股票域塞进 ``WindProvider`` 的报错现场（实测）::

    isError: 工具不存在: vserver_stock_data, market_call_tool

——报错指向「工具不存在」，真因是「走错了协议形状」。而按 URL 猜形状（见到
``vserver_stock_data`` 就改用直连）等于把协议差异埋在字符串匹配里，下个域再接进来必然
再错一次。故：**一家一 provider**，形状差异用 ``_wire`` 表达（这正是基类留的扩展点）。

## 复用与不复用

- 复用 :class:`WindProvider` 的 ``extract``：两个域的表格形状一致
  （``{"data": {"data": [{"columns": [...], "rows": [...]}]}}``），实测同形；
- 复用手鉴权头与协议版本（同一个 ``WIND_MCP_TOKEN`` 对两个域都有效，实测）；
- **不复用** ``_wire``（改为基类标准形状）与工具映射（本域没有二级网关）。
"""

import os
from typing import Any, Dict, Tuple

from app.services.mcp.base import McpProvider
from app.services.mcp.credentials import DataScope
from app.services.mcp.providers.wind import (
    WIND_CLIENT_INFO,
    WIND_PROTOCOL_VERSION,
    WindEndpointMissing,
    WindProvider,
)
from app.services.mcp.registry import register_provider

#: 股票域服务地址所在环境变量（**无默认值**，理由同 ``wind.py``：猜地址的失效形态是 DNS/WAF 报错）
WIND_STOCK_MCP_URL_ENV = 'WIND_STOCK_MCP_URL'

#: 能力名 → 上游工具名。**只登记实测确认过的**；下游按能力名取数，不写死工具名。
_CAPABILITY_TOOLS: Dict[str, str] = {
    # 个股/转债档案：一次问句给「申万一级 + 证监会门类」，传债券代码回正股行业（#2749）
    'stock_industry': 'get_stock_basicinfo',
    # 自然语言选股（按行业/概念/指标反查代码），留给人工探针与后续筛选页
    'stock_search': 'search_stocks',
}


@register_provider
class WindStockProvider(WindProvider):
    """Wind 股票数据 vserver：直连工具，无二级网关。"""

    name = 'wind_stock'
    protocol_version = WIND_PROTOCOL_VERSION
    client_info = WIND_CLIENT_INFO

    def base_url(self) -> str:
        url = (os.getenv(WIND_STOCK_MCP_URL_ENV) or '').strip()
        if not url:
            raise WindEndpointMissing(f'未设置环境变量 {WIND_STOCK_MCP_URL_ENV}', provider=self.name)
        return url

    def tool_for(self, capability: str) -> str:
        try:
            return _CAPABILITY_TOOLS[capability]
        except KeyError:
            known = ', '.join(sorted(_CAPABILITY_TOOLS))
            raise KeyError(f'Wind 股票域没有能力 {capability}（已知：{known}）') from None

    def scope_of(self, capability: str) -> DataScope:
        """个股档案 / 选股都是公开市场数据，用系统 Token。

        **不能** `super().scope_of()`：父类的判据是**父类模块**的 ``_CAPABILITY_TOOLS``，
        本域的能力不在那张表里，会一律落到基类默认的 ``USER_PRIVATE`` ——
        表现为「调用抛 McpUserTokenMissing」，看起来像凭据问题，真因是能力没登记在父表。
        故本类按**自己的**能力表判断；未知能力仍保守按用户私有（响亮失败，不烧系统额度）。
        """
        return DataScope.PUBLIC_MARKET if capability in _CAPABILITY_TOOLS else DataScope.USER_PRIVATE

    def _wire(self, tool: str, arguments: dict) -> Dict[str, Any]:
        """标准 JSON-RPC ``tools/call``（**不经** ``market_call_tool``）。

        见模块 docstring 的对照表：本域没有那个转发工具，调它只会拿到
        ``isError: 工具不存在``。
        """
        return McpProvider._wire(self, tool, arguments)

    @classmethod
    def capabilities(cls) -> Tuple[str, ...]:
        return tuple(sorted(_CAPABILITY_TOOLS))

    @classmethod
    def read_only_tool_names(cls) -> Tuple[str, ...]:
        return tuple(sorted(set(_CAPABILITY_TOOLS.values())))

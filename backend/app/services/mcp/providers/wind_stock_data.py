# -*- coding: utf-8 -*-
"""Wind **股票数据** vserver 的 provider（S5 / #2749）。

## 为什么不是复用 ``WindProvider`` 的名字

万得把数据按 vserver 分域部署，**两种域的协议形状不同**（2026-10-30 真机实测）：

=============================================  ==========================================
``/vserver_wind_tools``（聚合网关）              ``/vserver_stock_data``
=============================================  ==========================================
上游只暴露两个工具：``market_search_tools`` /   上游**直接**暴露 10 个数据工具
``market_call_tool``，数据查询必须经后者转发        （``get_stock_basicinfo`` / ``get_stock_kline`` …）
→ :class:`~app.services.mcp.providers.wind.WindProvider`  → 必须走标准 ``tools/call``，
                                                **没有** ``market_call_tool``
=============================================  ==========================================

把股票域塞进 ``WindProvider`` 的报错现场（实测）::

    isError: 工具不存在: vserver_stock_data, market_call_tool

——报错指向「工具不存在」，真因是「走错了协议形状」。而按 URL 猜形状（见到
``vserver_stock_data`` 就改用直连）等于把协议差异埋在字符串匹配里，下个域再接进来必然
再错一次。故：**一家一 provider**，形状差异用 ``_wire`` 表达。

> 2026-10-30 后续：该形状差异提为 :class:`~app.services.mcp.providers.wind_direct.WindDirectProvider`
> 基类，本类只声明「域 + 能力表」。地址解析、``_wire``、``tool_for``、``scope_of``
> 全部由基类承担 —— 再新接一个域不再需要复制这些逻辑。

## 能力表为什么只有两项

``vserver_stock_data`` 暴露 10 个工具，但本域真正有下游消费方的只有两个。其余
（``get_stock_fundamentals`` / ``get_stock_price_indicators`` / ``get_stock_events`` …）
**留白**：登记了没人调用就是死代码，等有页面或 job 真读它们时再补（#2749 的教训）。
"""

from typing import Dict

from app.services.mcp.providers.wind_direct import WindDirectProvider
from app.services.mcp.registry import register_provider

#: 单域地址定向覆盖（未设置则用 ``WIND_MCP_BASE`` + 本域路径）
WIND_STOCK_MCP_URL_ENV = 'WIND_STOCK_MCP_URL'

#: 能力名 → 上游工具名。**只登记实测确认过的**；下游按能力名取数，不写死工具名。
_CAPABILITY_TOOLS: Dict[str, str] = {
    # 个股/转债档案：一次问句给「申万一级 + 证监会门类」，传债券代码回正股行业（#2749）
    'stock_industry': 'get_stock_basicinfo',
    # 自然语言选股（按行业/概念/指标反查代码），留给人工探针与后续筛选页
    'stock_search': 'search_stocks',
}


@register_provider
class WindStockProvider(WindDirectProvider):
    """Wind 股票数据 vserver：直连工具，无二级网关。"""

    name = 'wind_stock'
    vserver = 'vserver_stock_data'
    url_env = WIND_STOCK_MCP_URL_ENV
    domain_label = 'Wind 股票域'
    tools = _CAPABILITY_TOOLS

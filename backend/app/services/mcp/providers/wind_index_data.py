# -*- coding: utf-8 -*-
"""Wind **指数数据** vserver 的 provider（S6 / #2749「行业 PE/PB 温度计」）。

## 与既有 ``WindProvider`` 的关系

``wind.py`` 已经能取指数**点位**（``index_kline`` / ``index_basicinfo`` /
``index_technicals``），但那三个能力是经 ``vserver_wind_tools`` 的二级网关
``market_call_tool`` 转发的。本域是**直连**形状，且提供网关侧没有的一个工具：
``get_index_fundamentals``（成份股加权估值）。

两者**不替换**：点位序列仍走 ``wind.py``（``index_daily_job`` 依赖它的
``period="10"`` 映射与 ``MATCH`` 列语义，实测过就不要动）；本域只补估值这一块。

## 实测口径（2026-10-30，必须记住的两条）

**① 「加权」这个词会把数值放大百倍。** 同一指数、同一交易日::

    问「沪深300 的市盈率」        → 最新市盈率PE_TTM = 12.8773   ✅
    问「沪深300 的加权市盈率」     → 指数加权市盈率  = 1917.8866  ❌（单位还标成 %）
    问「沪深300、中证500 的加权市盈率」→ 指数加权市盈率 = 19.18 / 20.34  ← 又正常了

单只正常、两只正常、三只放大百倍 —— 形态不稳定，无法用「哪种问法安全」归纳。
故 :mod:`app.services.adapters.wind_index_valuation` **一律不用「加权」二字**，
并对返回值做合理区间校验（PE 0~500、PB 0~50、股息率 0~30），超界即当作上游异常拒存，
而不是把 1917 当成 PE 写进温度计。

**② 列名随问法变化。** 只要 PE 时列名是「最新市盈率PE_TTM」；同时要 PB 时变成
「最新市盈率PE」；用名称（不写代码）查时又叫「最新市盈率」。故适配器按**谓词**认列，
不写死字符串。

## 顺带解决的分位需求

问「PE 和 PE 历史分位数」时，上游直接返回::

    历史每日市盈率 21.11 / 历史每日市盈率序号 1834 / 最大序号 10070
    / 最新市盈率在历史中的分位数 18.2044%

—— 分位数是上游算好的，不用我们自己攒历史序列。这是 #2749 清单里
「行业 PE/PB 温度计」最省事的一条路。
"""

from typing import Dict

from app.services.mcp.providers.wind_direct import WindDirectProvider
from app.services.mcp.registry import register_provider

#: 单域地址定向覆盖（未设置则用 ``WIND_MCP_BASE`` + 本域路径）
WIND_INDEX_MCP_URL_ENV = 'WIND_INDEX_MCP_URL'

#: 能力名 → 上游工具名（只登记有下游消费方的）
_CAPABILITY_TOOLS: Dict[str, str] = {
    # 成份股加权 PE / PB / 股息率 + 历史分位（温度计用）
    'index_valuation': 'get_index_fundamentals',
}


@register_provider
class WindIndexProvider(WindDirectProvider):
    """Wind 指数数据 vserver：直连工具，无二级网关。"""

    name = 'wind_index'
    vserver = 'vserver_index_data'
    url_env = WIND_INDEX_MCP_URL_ENV
    domain_label = 'Wind 指数域'
    tools = _CAPABILITY_TOOLS

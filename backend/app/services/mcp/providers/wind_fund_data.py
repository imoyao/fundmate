# -*- coding: utf-8 -*-
"""Wind **基金数据** vserver 的 provider（S6 / #2749「ETF 底层持仓」）。

## 为什么接这一域

``penetration.py`` 的 ``_PENETRABLE_TYPES`` 早就把 ``etf`` 列进可穿透类型，并在注释里
写明「ETF 目前无底层数据，仍走同一路径，**待 B3 补齐 ETF 持仓后自动生效，无需改这里**」。
本域就是那个补齐动作的上游：2026-10-30 真机实测 ``get_fund_holdings`` 对
``510300.SH`` 返回前十大重仓股（名称 / 股数 / 市值 / 名次）与资产类别占净值比
（股票 98.89% / 银行存款 1.08% / 债券 null），正好能写进 ``fund_holdings`` 表。

## 能力表为什么只有两项

``vserver_fund_data`` 实际暴露 10 个工具，但**登记了却没有下游消费方就是死代码**
（#2749 的原始抱怨）。故只登记两个现在真有落点的：

- ``fund_holdings`` → ``fund_holdings`` 表 → ``penetration`` 自动生效；
- ``fund_info`` → 跟踪指数 / 费率 / 现任经理（基金经理画像 #1970、费率核对）。

``get_fund_performance`` / ``get_fund_holders`` / ``search_funds`` 等留白：等有页面或 job
真的去读它们时再登记，不要把「能调」当成「该接」。

## 入参形态

本域的数据工具**全部只吃一个自然语言 ``question``**（其余 8 个域同理），没有结构化入参。
故 :mod:`app.services.adapters.wind_fund` 负责把「代码 + 报告期」拼成问句，
**并且必须容忍返回列名随问法变化**（实测：同一指标有时叫「最新市盈率PE_TTM」、
有时叫「最新市盈率PE」、有时叫「最新市盈率」）。
"""

from typing import Dict

from app.services.mcp.providers.wind_direct import WindDirectProvider
from app.services.mcp.registry import register_provider

#: 单域地址定向覆盖（未设置则用 ``WIND_MCP_BASE`` + 本域路径）
WIND_FUND_MCP_URL_ENV = 'WIND_FUND_MCP_URL'

#: 能力名 → 上游工具名（只登记**有下游消费方**的，理由见模块 docstring）
_CAPABILITY_TOOLS: Dict[str, str] = {
    # 披露持仓族（重仓股 / 重仓债 / FOF 重仓基金）+ 资产类别构成
    'fund_holdings': 'get_fund_holdings',
    # 产品档案：投资类型与风格、跟踪指数、费率、现任基金经理、管理人
    'fund_info': 'get_fund_info',
}


@register_provider
class WindFundProvider(WindDirectProvider):
    """Wind 基金数据 vserver：直连工具，无二级网关。"""

    name = 'wind_fund'
    vserver = 'vserver_fund_data'
    url_env = WIND_FUND_MCP_URL_ENV
    domain_label = 'Wind 基金域'
    tools = _CAPABILITY_TOOLS

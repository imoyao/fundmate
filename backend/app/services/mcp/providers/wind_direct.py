# -*- coding: utf-8 -*-
"""Wind **直连域** provider 基类（S6 / 多 vserver 接入，2026-10-30 真机实测）。

## 为什么需要这一层

万得把数据按 vserver 分域部署，实测 17 个端点后只有 **10 个**真能拉到工具
（另 8 个能握手、鉴权也过，但 ``tools/list`` 返回空数组 —— 是订阅范围问题，不是故障）。
这 10 个里又只有 **两种**协议形状：

=========================================  ============================================
``/vserver_wind_tools``（聚合网关）          其余 9 个域（直连）
=========================================  ============================================
只暴露 ``market_search_tools`` /            直接暴露 ``get_fund_holdings`` /
``market_call_tool``，数据查询必须经后者转发   ``get_index_fundamentals`` … 等真工具
→ :class:`~app.services.mcp.providers.wind.WindProvider`  |  → 本模块的 :class:`WindDirectProvider`
=========================================  ============================================

除这两点外，9 个直连域**没有任何差别**：同 host、同 Bearer、同无状态 SSE
（``wind-mcp-streamable-http-stateless`` 1.25.0，无 ``Mcp-Session-Id``）、
同 ``{"data": {"data": [{"columns": [...], "rows": [...]}]}}`` 表格形状、同 ``isError`` 约定。
故新增一个域的成本应该是「一个 ``vserver`` 字符串 + 一张能力表」，而不是再复制一遍解析逻辑
—— 这也正是把 ``wind_stock_data.py`` 的私有实现提上来的原因。

## 地址：为什么现在可以有默认值

``wind.py`` 当年拒绝给地址默认值，理由是「仓库里没有可确认的 Wind 网关地址常量，猜一个
的失效形态是 DNS/WAF 报错」。那条判断在当时成立，但对**直连域**已经不成立：域名与
``/vserver_{域}/mcp/`` 路径是 2026-10-30 逐个真机验证过的固定布局，不是部署参数。

更关键的是运维后果：如果每个域都要求一个 ``WIND_XXX_MCP_URL``，那么任何新接的域
**默认就是死代码** —— 代码合了、测试绿了、线上一次也不会被调用（#2749 的原始形态）。
故本类的取值顺序是：

1. ``WIND_MCP_BASE``（部署级覆盖，比如内网代理）→
2. 内置默认 :data:`WIND_DEFAULT_BASE` —— 已实测，不再靠猜；
3. 单个域仍可用 :attr:`WindDirectProvider.url_env` 指向的变量做**定向覆盖**
   （本地 mock / 灰度切换），未设置就走上面两条。

失败的只剩 **Token 缺失**这一种（``McpTokenMissing``），而它本来就是必须人工配置的东西。

## 能力表由子类声明，不继承

父类 :meth:`WindProvider.scope_of` 的判据是**父类模块**的 ``_CAPABILITY_TOOLS``；
子类能力不在那张表里会一律落到 ``USER_PRIVATE``，表现是「调用抛 ``McpUserTokenMissing``」，
看起来像凭据问题、真因是能力没登记在父表（实测踩过）。故本类按 ``cls.tools`` 判断。
"""

import os
from typing import Any, Dict, Tuple

from app.services.mcp.base import McpProvider
from app.services.mcp.credentials import DataScope
from app.services.mcp.providers.wind import WIND_CLIENT_INFO, WIND_PROTOCOL_VERSION, WindProvider

#: 部署级服务根地址（内网代理 / 灰度时覆盖；未设置用内置默认）
WIND_BASE_ENV = 'WIND_MCP_BASE'
#: **已实测**的万得 MCP 根地址（2026-10-30：17 个端点逐个 initialize + tools/list 验证）
WIND_DEFAULT_BASE = 'https://mcp.wind.com.cn'


def wind_base() -> str:
    """服务根地址（去掉尾部斜杠），未配置则用已实测的默认值。"""
    return ((os.getenv(WIND_BASE_ENV) or '').strip() or WIND_DEFAULT_BASE).rstrip('/')


class WindDirectProvider(WindProvider):
    """Wind 直连域：一个 vserver + 一张能力表，其余全部复用。

    **本类不注册**（``register_provider`` 遇到空 ``name`` 会直接抛错）——注册发生在子类。

    子类只声明三件事::

        class WindFundProvider(WindDirectProvider):
            name = 'wind_fund'
            vserver = 'vserver_fund_data'
            tools = {'fund_holdings': 'get_fund_holdings'}

    ``url_env`` 是可选的定向覆盖点，不声明就没有。
    """

    #: 注册表键 / 日志归属（``mcp_call_logs.provider``）
    name = ''
    #: vserver 路径段（``https://host/**vserver_fund_data**/mcp/``）
    vserver = ''
    #: 单域地址覆盖变量名（可选；不声明则只用 ``WIND_MCP_BASE``）
    url_env = ''
    #: 能力名 → 上游工具名（**只登记实测确认过的**）
    tools: Dict[str, str] = {}
    #: 报错文案里的中文域名（``tool_for`` 的提示用）
    domain_label = ''

    protocol_version = WIND_PROTOCOL_VERSION
    client_info = WIND_CLIENT_INFO

    def base_url(self) -> str:
        override = (os.getenv(self.url_env) or '').strip() if self.url_env else ''
        if override:
            return override
        if not self.vserver:
            raise ValueError(f'{type(self).__name__} 未声明 vserver')
        return f'{wind_base()}/{self.vserver}/mcp/'

    def tool_for(self, capability: str) -> str:
        try:
            return type(self).tools[capability]
        except KeyError:
            known = ', '.join(sorted(type(self).tools))
            label = self.domain_label or self.name
            raise KeyError(f'{label} 没有能力 {capability}（已知：{known}）') from None

    def scope_of(self, capability: str) -> DataScope:
        """已登记能力一律公开市场数据（行情 / 估值 / 档案），用系统 Token。

        见模块 docstring：判据必须是**本类**的 ``tools``，不能 ``super()``。
        未知能力保守落到 ``USER_PRIVATE`` —— 响亮失败，不悄悄烧系统额度。
        """
        return DataScope.PUBLIC_MARKET if capability in type(self).tools else DataScope.USER_PRIVATE

    def _wire(self, tool: str, arguments: dict) -> Dict[str, Any]:
        """标准 JSON-RPC ``tools/call``（直连域**没有** ``market_call_tool``）。"""
        return McpProvider._wire(self, tool, arguments)

    @classmethod
    def capabilities(cls) -> Tuple[str, ...]:
        return tuple(sorted(cls.tools))

    @classmethod
    def read_only_tool_names(cls) -> Tuple[str, ...]:
        return tuple(sorted(set(cls.tools.values())))

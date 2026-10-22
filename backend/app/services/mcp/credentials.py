# -*- coding: utf-8 -*-
"""MCP 凭据路由（S2）：取谁的 Token 由 ``data_scope()`` 决定，不由调用点 if/else 决定。

设计文档 ``docs/dev/mcp-integration.md`` §5.1。S2 只落地**系统凭据**（env）这一侧；
用户私有凭据表 ``user_mcp_credentials`` 在 S5，但**分支现在就写死**，因为它的价值不是
"能取到值"，而是「用户没配 Token 时**不可能**悄悄用系统 Token 代取」——
这条必须是类型级保证（抛 ``McpUserTokenMissing``），不能是注释级约定，否则 S5 接表时
任何一处漏判都会把系统额度记到用户私有请求上，且数据归属错乱（别人的账户数据算到系统头上）。

三条硬约束：

1. **本模块绝不记录 token**（含异常文案、日志、行号上下文）；
2. **未知 provider 抛错**，不按 ``{NAME}_MCP_TOKEN`` 猜：新增一家服务时补一行映射，
   "猜"会让「没配」与「配错变量名」在故障现场无法区分；
3. ``is_configured()`` 只回答有没有，不返回值 —— ``/api/health`` 是免登录端点。
"""

import os
from enum import StrEnum
from typing import Optional

from app.services.mcp.errors import McpTokenMissing, McpUserTokenMissing


class DataScope(StrEnum):
    """能力的数据归属（决定用谁的钱 / 谁的额度）。"""

    PUBLIC_MARKET = 'public_market'  # 指数 / 估值 / 基金净值档案：公开市场数据
    PLATFORM_PUBLIC = 'platform_public'  # 平台公开策略（且慢投顾组合）：系统 Token 共享
    USER_PRIVATE = 'user_private'  # 用户账户 / 持仓 / 自选 / 个人额度：**必须**用户 Token


#: provider → 系统凭据所在环境变量（新增服务在这里登记，不猜变量名）
_TOKEN_ENV = {
    'qieman': 'QIEMAN_API_KEY',
    'wind': 'WIND_MCP_TOKEN',
}


def token_env_name(provider: str) -> str:
    """provider 对应的系统凭据环境变量名。

    Raises:
        ValueError: provider 未登记（新接一家 MCP 时必须显式补映射）。
    """
    try:
        return _TOKEN_ENV[provider]
    except KeyError:
        known = ', '.join(sorted(_TOKEN_ENV))
        raise ValueError(f'provider {provider!r} 未登记凭据环境变量（已知：{known}）') from None


def is_configured(provider: str) -> bool:
    """系统凭据是否已配置（只看有无；health 端点读它，禁止返回值）。"""
    try:
        env_name = token_env_name(provider)
    except ValueError:
        return False
    return bool((os.getenv(env_name) or '').strip())


def system_token(provider: str) -> str:
    """取系统 Token。

    Raises:
        McpTokenMissing: 未配置（可选组件不可用，不是服务故障）。
    """
    env_name = token_env_name(provider)
    token = (os.getenv(env_name) or '').strip()
    if not token:
        raise McpTokenMissing(f'未设置环境变量 {env_name}', provider=provider)
    return token


def resolve_token(provider: str, scope: 'DataScope | str', user_id: Optional[str] = None) -> str:
    """按数据归属取凭据（唯一的凭据入口）。

    Args:
        provider: 服务标识（``qieman`` / ``wind``）。
        scope: 能力的数据归属，字符串或 :class:`DataScope` 均可。
        user_id: 用户私有能力时的用户标识（S5 用它查表；S2 只用于报错定位）。

    Raises:
        McpUserTokenMissing: ``USER_PRIVATE`` 且用户没配 Token —— **不回退系统 Token**。
        McpTokenMissing: 系统 Token 未配置。
        ValueError: 未知 scope。

    Note:
        判据是 ``scope`` 而不是 ``provider``：同一家服务可以既有公开能力又有私有能力
        （Wind 的指数点位 vs 用户账户持仓），按 provider 分支必然错。
    """
    normalized = DataScope(scope)
    if normalized is DataScope.USER_PRIVATE:
        # S5 才接 user_mcp_credentials；在那之前**任何**用户私有能力都不可用，
        # 且必须抛错而不是回退 —— 回退是这条红线唯一真正的失效方式。
        raise McpUserTokenMissing('用户凭据表尚未接入（S5）', provider=provider)
    return system_token(provider)

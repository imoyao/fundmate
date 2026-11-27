# -*- coding: utf-8 -*-
"""MCP 凭据路由（S2/S5）：取谁的 Token 由 ``data_scope()`` 决定，不由调用点 if/else 决定。

设计文档 ``docs/dev/mcp-integration.md`` §5.1。系统凭据（env）在本模块；用户私有分支
**必须**抛 ``McpUserTokenMissing`` 而不是回退系统 Token（类型级保证，否则系统额度被用户私有请求消耗）。

S5 后该分支下沉到 ``services/mcp/user_credentials``（Fernet / 过期 / user_id 隔离；
浏览器 OAuth2 与用户粘贴 API Key 由 auth_type 区分），本文件只做路由，不 import 模型与 DB。

三条硬约束：

1. **本模块绝不记录 token**（含异常文案、日志、行号上下文）；
2. **未知 provider 抛错**，不按 ``{NAME}_MCP_TOKEN`` 猜；
3. ``is_configured()`` 只回答有没有，不返回值 —— ``/api/health`` 是免登录端点。
"""

import os
from enum import StrEnum
from typing import Optional

from app.services.mcp.errors import McpTokenMissing
from app.services.mcp.user_credentials import user_token


class DataScope(StrEnum):
    """能力的数据归属（决定用谁的钱 / 谁的额度）。"""

    PUBLIC_MARKET = 'public_market'  # 指数 / 估值 / 基金净值档案：公开市场数据
    PLATFORM_PUBLIC = 'platform_public'  # 平台公开策略（且慢投顾组合）：系统 Token 共享
    USER_PRIVATE = 'user_private'  # 用户账户 / 持仓 / 自选 / 个人额度：**必须**用户 Token


#: provider → 系统凭据所在环境变量（新增服务在这里登记，不猜变量名）
#:
#: ``wind`` 与 ``wind_stock`` 是**同一张 Token、不同 vserver**（实测：同一个 Bearer 对
#: 指数 / 宏观 / 股票 / 债券 / 基金五个域都有效）。分成两个 provider 是因为协议形状不同
#: （见 ``providers/wind_stock_data.py``），但凭据同源——照抄同一个变量名，避免多一份密钥。
_TOKEN_ENV = {
    'qieman': 'QIEMAN_API_KEY',
    'wind': 'WIND_MCP_TOKEN',
    'wind_stock': 'WIND_MCP_TOKEN',
    'wind_fund': 'WIND_MCP_TOKEN',
    'wind_index': 'WIND_MCP_TOKEN',
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
        # 红线：取不到就抛错，绝不回退系统 Token。
        # 解密 / 过期 / 按 user_id 隔离都在 user_credentials，路由层不感知凭据形状。
        return user_token(user_id, provider)
    return system_token(provider)

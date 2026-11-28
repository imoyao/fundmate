# -*- coding: utf-8 -*-
"""OAuth 用户凭据的校验路由（#3304）。

同一 provider 的两种凭据指向**不同网关**：API Key（``static_token``）走 provider
registry 的平台端点（``x-api-key``，平台公开数据）；浏览器授权（``oauth2``）拿到的
是**用户私有** token，只能打 partner 网关（``Authorization: Bearer``）。provider 的
``base_url`` / ``auth_headers`` 服务于数据面（按 capability 取数），感知不到认证
方式，所以按 provider 在这里单点登记「OAuth 凭据该打哪个端点、带头什么」。

未登记的 OAuth provider 返回 ``None``，回落 provider 默认端点——tzzb 的 OAuth
端点与数据面是同一台主机（同一注册表），行为等价。
"""

from typing import Callable, Dict, Optional, Tuple

#: (端点, 请求头工厂)。headers 只含鉴权与来源伪装，通用头（Accept/UA）由
#: 调用方（connection_check）统一补，避免两处漂移。
Route = Tuple[str, Dict[str, str]]


def _qieman_route(token: str) -> Route:
    """且慢 partner 网关：Bearer + Origin/Referer（且慢网关按来源判 WAF，见
    ``providers/qieman.py`` 的同名处理；partner 端点同族，保持同形状）。"""
    base = 'https://stargate-partner.yingmi.com/mcp/v2/oauth/qieman'
    return (
        base,
        {
            'Authorization': f'Bearer {token}',
            'Origin': base,
            'Referer': base + '/',
        },
    )


_ROUTES: Dict[str, Callable[[str], Route]] = {
    'qieman': _qieman_route,
}


def resolve_connection_route(provider: str, auth_type: Optional[str], token: str) -> Optional[Route]:
    """OAuth 凭据 → (端点, 请求头)；static_token / 未登记返回 ``None`` 走默认。"""
    if auth_type != 'oauth2':
        return None
    factory = _ROUTES.get(provider)
    if factory is None:
        return None
    return factory(token)

# -*- coding: utf-8 -*-
"""MCP 浏览器授权编排（S5b）：DCR / PKCE / state / 回调 / 刷新 / 撤销。

设计文档 ``docs/dev/mcp-connection-management.md`` §3。本模块只负责**拿 token**，
拿到之后交给 ``user_credentials.save_oauth_token`` 加密落库；它不感知 API Key 型
连接，也不碰传输层。

三条安全约束：

1. **回调不携带 JWT**：``state`` 是唯一能证明"这次回调属于哪个用户"的凭据，
   因此必须随机、绑定 user_id、5 分钟过期、一次性消费（落库，非内存）；
2. **PKCE verifier 加密存库**：只在 token 交换时解密，绝不进日志；
3. **不回显上游报文**：token 端点可能把 token 塞进错误体，这里只记 HTTP 状态，
   异常文案固定为中文人话（沿用 ``McpError`` 的脱敏纪律）。

provider 地址是**代码常量**，不接受调用方传 URL（SSRF 红线）。DCR 的 client_id
落库持久化（``mcp_oauth_clients``）：refresh_token 绑定注册时的 client_id，
重启后必须复用同一 id，否则存量用户的刷新全部失效。
"""

import os
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterator, Optional, Tuple

import requests
from loguru import logger
from sqlalchemy import and_

from app.core.database import user_session
from app.core.time_utils import now_shanghai
from app.models.mcp_oauth_state import McpOAuthState
from app.services.mcp.errors import McpAuthError, McpUserTokenMissing
from app.services.mcp.oauth_client_store import read_client_id, save_client_id
from app.services.mcp.user_credentials import (
    DEFAULT_STATE_TTL,
    decrypt_payload,
    delete_credential,
    encrypt_payload,
    load_credential,
    pkce_pair,
    save_oauth_token,
    validate_token_endpoint,
)


#: 浏览器跳转型 provider 的固定登记（无 url 入参，防 SSRF）。
#: 新增一家服务必须在这里补一段常量，不接受用户在界面上填地址。
@dataclass(frozen=True)
class OAuthProviderConfig:
    name: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str
    revocation_endpoint: Optional[str]
    scope: str = 'tools.read'
    #: RFC 9728 发现的受保护资源标识符（RFC 8707 的 resource 参数值）。
    #: 为空表示上游不强制资源指示，请求里就不带该参数。
    resource: Optional[str] = None

    def redirect_uri(self) -> str:
        """回调地址来自环境配置（部署域名不同），默认本地开发地址。"""
        return (os.getenv('MCP_OAUTH_REDIRECT_URI') or 'http://127.0.0.1:5000/api/mcp/oauth/callback/').strip()


PROVIDERS: Dict[str, OAuthProviderConfig] = {
    'tzzb': OAuthProviderConfig(
        name='tzzb',
        authorization_endpoint='https://tzzb.10jqka.com.cn/oauth2/authorize',
        token_endpoint='https://tzzb.10jqka.com.cn/oauth2/token',
        registration_endpoint='https://tzzb.10jqka.com.cn/oauth2/register',
        revocation_endpoint='https://tzzb.10jqka.com.cn/oauth2/revoke',
    ),
    # 盈米 partner 网关（#3304）：四端点实测自 /.well-known/openid-configuration，
    # DCR 实测可注册（token_endpoint_auth_method=none），DPoP/PAR 均 False。
    # scope 取保护资源元数据声明的 oapqieman:level1（最小权限），offline_access
    # 换取 refresh_token——上游 refresh 是否可用待真实授权后验证（tzzb 是
    # invalid_grant，不能想当然）。
    # RFC 9728 资源发现：GET /.well-known/oauth-protected-resource/mcp/v2/oauth/qieman
    # → {"resource": "https://stargate-partner.yingmi.com/mcp/v2/oauth/qieman"}。
    # 该网关强制 RFC 8707：authorize 不带 resource 直接 invalid_target。
    'qieman': OAuthProviderConfig(
        name='qieman',
        authorization_endpoint='https://stargate-partner.yingmi.com/oauth/authorize',
        token_endpoint='https://stargate-partner.yingmi.com/oauth/token',
        registration_endpoint='https://stargate-partner.yingmi.com/oauth/register',
        revocation_endpoint='https://stargate-partner.yingmi.com/oauth/revoke',
        scope='oapqieman:level1 offline_access',
        resource='https://stargate-partner.yingmi.com/mcp/v2/oauth/qieman',
    ),
}


def supported_providers() -> Tuple[str, ...]:
    """可由浏览器授权连接的 provider（管理页只列这些）。"""
    return tuple(sorted(PROVIDERS))


def provider_config(provider: str) -> OAuthProviderConfig:
    """取 provider 配置；未登记直接抛错，不猜地址。"""
    try:
        return PROVIDERS[provider]
    except KeyError:
        raise ValueError(f'provider {provider!r} 不支持浏览器授权') from None


def _resource_param(config: OAuthProviderConfig) -> Dict[str, str]:
    """RFC 8707 资源指示：authorize 与 token 请求必须指向同一资源。

    值来自上面的 RFC 9728 发现结果，不接受调用方传参（防 SSRF / 越权指定
    audience）。DCR 不属于 RFC 8707 登记的参数位置，注册请求不带。
    """
    return {'resource': config.resource} if config.resource else {}


def _http_post(url: str, data: Dict[str, Any], as_json: bool = False) -> Dict[str, Any]:
    """唯一的上游 POST 出口（测试在这里打桩，不 mock requests 全局）。

    所有 endpoint 都先经 :func:`validate_token_endpoint` 校验过白名单域名。
    编码由端点协议决定，不能一刀切：DCR 按 RFC 7591 要求 **JSON body**，
    token 端点按 RFC 6749 §4.1.3 必须 **form 编码**——用错编码上游就 400。
    """
    body = {'json': data} if as_json else {'data': data}
    response = requests.post(url, timeout=15, **body)
    if response.status_code >= 400:
        # 只记状态码，绝不记 response.text：上游错误体可能含 token。
        logger.warning(f'MCP OAuth 上游返回 {response.status_code}（{url.rsplit("/", 1)[-1]}）')
        raise McpAuthError('授权服务拒绝了本次请求，请重新连接', provider='oauth')
    try:
        payload = response.json()
    except ValueError:
        raise McpAuthError('授权服务返回格式异常，请重新连接', provider='oauth') from None
    if not isinstance(payload, dict):
        raise McpAuthError('授权服务返回格式异常，请重新连接', provider='oauth')
    return payload


def client_id_for(config: OAuthProviderConfig) -> str:
    """client_id 的真相源：env 预置 > 库（上次注册结果）> DCR 注册并落库。

    为什么必须持久化：``refresh_token`` 绑定注册时的 client_id（``none``
    客户端刷新必须携带原 id）——重启后换新 id 会让存量 refresh_token
    全部失效，等价于每次发版强制全体用户重连。存取细节在
    :mod:`app.services.mcp.oauth_client_store`（唯一约束兜并发注册）。
    """
    preset = (os.getenv(f'MCP_{config.name.upper()}_CLIENT_ID') or '').strip()
    if preset:
        return preset
    stored = read_client_id(config.name)
    if stored:
        return stored
    payload = _http_post(
        config.registration_endpoint,
        {
            'redirect_uris': [config.redirect_uri()],
            'client_name': '多多贝投资账本',
            'grant_types': ['authorization_code', 'refresh_token'],
            'response_types': ['code'],
            'token_endpoint_auth_method': 'none',
        },
        as_json=True,
    )
    client_id = payload.get('client_id')
    if not isinstance(client_id, str) or not client_id:
        raise McpAuthError('授权服务未完成注册，请稍后重试', provider='oauth')
    return save_client_id(config.name, client_id)


@contextmanager
def _write_session() -> Iterator[Any]:
    """请求内复用 user_session；非请求上下文（测试 / CLI）显式提交。"""
    with user_session() as db:
        try:
            yield db
            try:
                from flask import has_request_context
            except ImportError:  # pragma: no cover
                has_request_context = lambda: False  # noqa: E731
            if not has_request_context():
                db.commit()
        except Exception:
            db.rollback()
            raise


def _now_naive() -> datetime:
    return now_shanghai().replace(tzinfo=None)


def begin(provider: str, user_id: int) -> Dict[str, Any]:
    """发起授权：DCR → PKCE → 落 state → 返回浏览器授权 URL。

    ``state`` 与 verifier 分离保存：URL 里只有 state，verifier 加密落库，
    回调时再取出来换 token（PKCE 的关键就是 verifier 只在本机出现过）。
    """
    config = provider_config(provider)
    validate_token_endpoint(config.token_endpoint, provider)
    client_id = client_id_for(config)
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    expires_at = _now_naive() + DEFAULT_STATE_TTL

    with _write_session() as db:
        db.add(
            McpOAuthState(
                state=state,
                user_id=user_id,
                provider=provider,
                verifier_cipher=encrypt_payload({'verifier': verifier}, current_version()),
                key_version=current_version(),
                expires_at=expires_at,
            )
        )
        db.flush()

    from urllib.parse import urlencode

    query = urlencode(
        {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': config.redirect_uri(),
            'scope': config.scope,
            'state': state,
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
            **_resource_param(config),
        }
    )
    return {
        'authorization_url': f'{config.authorization_endpoint}?{query}',
        'state': state,
        'expires_in': int(DEFAULT_STATE_TTL.total_seconds()),
    }


def current_version() -> int:
    """复用凭据模块的密钥版本（state 与凭据共用一套密钥，少一处配置）。"""
    from app.services.mcp.user_credentials import current_key_version

    return current_key_version()


def _consume_state(provider: str, state: str) -> Tuple[int, str]:
    """原子消费 state：条件 UPDATE 保证并发下只有一个请求能成功。"""
    if not state or len(state) > 100:
        raise McpAuthError('授权请求无效，请重新发起连接', provider='oauth')
    with _write_session() as db:
        updated = (
            db.query(McpOAuthState)
            .filter(
                and_(
                    McpOAuthState.state == state,
                    McpOAuthState.provider == provider,
                    McpOAuthState.used_at.is_(None),
                )
            )
            .update({'used_at': _now_naive()}, synchronize_session=False)
        )
        if not updated:
            raise McpAuthError('授权请求无效或已使用，请重新发起连接', provider='oauth')
        row = db.query(McpOAuthState).filter_by(state=state).one()
        if row.expires_at <= _now_naive():
            raise McpAuthError('授权请求已超时，请重新发起连接', provider='oauth')
        verifier = decrypt_payload(row.verifier_cipher, row.key_version).get('verifier')
        if not verifier:
            raise McpAuthError('授权请求数据损坏，请重新发起连接', provider='oauth')
        return row.user_id, verifier


def provider_for_state(state: str) -> Optional[str]:
    """回调反查 provider：上游只回 state/code，provider 在发起时绑进了 state 行。

    为什么不能猜（``supported_providers()[0]``）：排序随登记顺序漂移，两家以上
    OAuth provider 后必然拿别的服务的 state 来消费——这是双 provider 化（#3304）
    时在测试网里现形的存量缺陷，修法就是「provider 只信 state 行」。
    """
    if not state or len(state) > 100:
        return None
    with _write_session() as db:
        row = (
            db.query(McpOAuthState.provider)
            .filter(
                and_(
                    McpOAuthState.state == state,
                    McpOAuthState.used_at.is_(None),
                )
            )
            .first()
        )
        return row[0] if row else None


def callback(provider: str, state: str, code: str) -> int:
    """授权回调：校验 state → code 换 token → 加密入库；返回所属 user_id。"""
    config = provider_config(provider)
    if not code:
        raise McpAuthError('授权未携带有效凭证，请重新发起连接', provider='oauth')
    user_id, verifier = _consume_state(provider, state)
    payload = _http_post(
        config.token_endpoint,
        {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': config.redirect_uri(),
            'client_id': client_id_for(config),
            'code_verifier': verifier,
            **_resource_param(config),
        },
    )
    access_token = payload.get('access_token')
    if not isinstance(access_token, str) or not access_token:
        raise McpAuthError('授权服务未返回可用凭证，请重新发起连接', provider='oauth')
    save_oauth_token(
        user_id,
        provider,
        access_token=access_token,
        refresh_token=payload.get('refresh_token'),
        expires_in=payload.get('expires_in'),
        token_endpoint=config.token_endpoint,
    )
    return user_id


def refresh(provider: str, user_id: int) -> None:
    """用 refresh_token 换新 access_token；没有 refresh_token 时要求重连。

    必须以 ``allow_expired=True`` 读凭据：access_token 过期后 refresh_token
    仍然有效，若按默认口径读，过期凭据自己就取不出 refresh_token（死锁）。
    """
    config = provider_config(provider)
    cred = load_credential(user_id, provider, allow_expired=True)
    if cred is None:
        raise McpUserTokenMissing('用户尚未连接该服务', provider=provider)
    if not cred.refresh_token:
        raise McpAuthError('授权已失效，请重新连接', provider=provider)
    payload = _http_post(
        config.token_endpoint,
        {
            'grant_type': 'refresh_token',
            'refresh_token': cred.refresh_token,
            'client_id': client_id_for(config),
            **_resource_param(config),
        },
    )
    access_token = payload.get('access_token')
    if not isinstance(access_token, str) or not access_token:
        raise McpAuthError('授权服务未返回可用凭证，请重新连接', provider='oauth')
    save_oauth_token(
        user_id,
        provider,
        access_token=access_token,
        refresh_token=payload.get('refresh_token') or cred.refresh_token,
        expires_in=payload.get('expires_in'),
        token_endpoint=config.token_endpoint,
    )


def revoke(provider: str, user_id: int) -> None:
    """断开连接：先通知上游撤销（失败不阻断本地删除），再删本地凭据。

    ``allow_expired=True``：过期恰恰是最需要断开的时刻（用户得先断开才能重连），
    读凭据不能被 access_token 过期短路——与刷新编排同款理由。
    """
    config = provider_config(provider)
    cred = load_credential(user_id, provider, allow_expired=True)
    if cred is None:
        return
    if config.revocation_endpoint:
        try:
            _http_post(
                config.revocation_endpoint,
                {'token': cred.token, 'token_type_hint': 'access_token', 'client_id': client_id_for(config)},
            )
        except McpAuthError:
            logger.warning('MCP 授权撤销失败，仍删除本地凭据')
    delete_credential(user_id, provider)

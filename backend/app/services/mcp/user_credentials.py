# -*- coding: utf-8 -*-
"""用户私有 MCP 凭据的加密存储与读取（S5a/S5b，多用户隔离）。

设计文档 ``docs/dev/mcp-connection-management.md`` §2。这是 ``user_mcp_credentials``
表的**唯一**读写方；其他模块不得直接 query 这张表，否则「解密 / 过期 / 密钥版本」
三件事会被各处重复实现，且极易有人把明文写进日志。

两种连接方式共用本模块，差别只在凭据形状：

- ``oauth2``：浏览器跳转授权码流程 → access_token（+ refresh_token / 过期时间）；
- ``static_token``：用户在连接管理页粘贴的 API Key → 无过期、无刷新。

三条硬约束：

1. **明文不出本模块**：返回值只给 token 字符串本身，任何日志 / 异常 / API 响应
   不得出现密文或明文；错误文案只说「未连接 / 已过期」，不回显内容。
2. **按 user_id 隔离**：所有查询都带 ``user_id``；不存在「按 provider 取最新一条」
   这种会跨用户串号的入口。
3. **缺密钥即报错，绝不降级明文存储**：``MCP_CREDENTIAL_KEY`` 未配置时直接抛
   :class:`CredentialKeyMissing`，而不是把 token 原样塞进库——那会把「加密」变成
   注释级约定。

密钥轮换：当前版本由 ``MCP_CREDENTIAL_KEY_VERSION``（默认 1）指定，
版本 N 的密钥读 ``MCP_CREDENTIAL_KEY_V<N>``；版本 1 兼容 ``MCP_CREDENTIAL_KEY``。
每条记录自带 ``key_version``，解密时按行内版本取密钥，故轮换期间旧行仍可读。
"""

import base64
import hashlib
import json
import os
import secrets
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterator, Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import and_

from app.core.database import user_session
from app.core.time_utils import now_shanghai
from app.models.user_mcp_credential import UserMcpCredential
from app.services.mcp.errors import McpAuthError, McpUserTokenMissing

#: 本表支持的认证方式。CLI 登录型（天天基金 ttskill）**不进本表**——
#: 它的登录态在 CLI 进程手里，写一行「已连接」是假连接（设计文档 §1.3）。
AUTH_TYPES = ('oauth2', 'static_token')

#: 允许写入 token_endpoint 的域名白名单（SSRF 边界）。
#: 新增服务必须在这里显式登记 https 域名，不接受用户自带 URL。
_TOKEN_ENDPOINT_HOSTS: Dict[str, str] = {
    'tzzb': 'tzzb.10jqka.com.cn',
}

#: state / PKCE 的一次性参数有效期（授权编排层复用）。
DEFAULT_STATE_TTL = timedelta(minutes=5)


class CredentialKeyMissing(RuntimeError):
    """加密密钥未配置——必须配置后重试，绝不降级为明文存储。"""


class CredentialCorrupt(RuntimeError):
    """密文无法解密（密钥轮换后旧密钥已删，或数据被篡改）。"""


@dataclass(frozen=True)
class UserCredential:
    """解密后的凭据（只在内存中存在，禁止整体进日志）。"""

    provider: str
    auth_type: str
    #: ``repr=False`` 是红线：dataclass 默认 repr 会把 token 打进日志 / traceback。
    token: str = field(repr=False)
    refresh_token: Optional[str] = field(default=None, repr=False)
    expires_at: Optional[datetime] = None
    token_endpoint: Optional[str] = None
    key_version: int = 1


def current_key_version() -> int:
    """当前加密密钥版本（写入用）。"""
    raw = (os.getenv('MCP_CREDENTIAL_KEY_VERSION') or '1').strip()
    try:
        version = int(raw)
    except ValueError:
        raise CredentialKeyMissing('MCP_CREDENTIAL_KEY_VERSION 必须是整数') from None
    if version < 1:
        raise CredentialKeyMissing('MCP_CREDENTIAL_KEY_VERSION 必须 >= 1')
    return version


def _fernet_for(version: int) -> Fernet:
    """按版本取 Fernet；缺密钥抛 :class:`CredentialKeyMissing`（不回退明文）。"""
    env_name = 'MCP_CREDENTIAL_KEY' if version == 1 else f'MCP_CREDENTIAL_KEY_V{version}'
    raw = (os.getenv(env_name) or '').strip()
    if not raw:
        raise CredentialKeyMissing(f'未配置 {env_name}，无法加解密用户 MCP 凭据')
    try:
        return Fernet(raw.encode('ascii'))
    except (ValueError, TypeError) as exc:
        raise CredentialKeyMissing(f'{env_name} 不是合法的 Fernet 密钥') from exc


def encrypt_payload(payload: Dict[str, Any], version: int) -> str:
    """JSON → Fernet 密文（str，可直接落 Text 列）。"""
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    return _fernet_for(version).encrypt(raw.encode('utf-8')).decode('ascii')


def decrypt_payload(cipher_text: str, version: int) -> Dict[str, Any]:
    """Fernet 密文 → JSON；密钥错 / 密文损坏都抛 :class:`CredentialCorrupt`。

    异常文案**不含密文**：把密文带进日志等于给攻击者省掉一步离线破解。
    """
    try:
        plain = _fernet_for(version).decrypt(cipher_text.encode('ascii'))
    except (InvalidToken, ValueError, TypeError) as exc:
        raise CredentialCorrupt(f'MCP 凭据密文无法解密（key_version={version}）') from exc
    try:
        data = json.loads(plain.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CredentialCorrupt(f'MCP 凭据明文格式损坏（key_version={version}）') from exc
    if not isinstance(data, dict):
        raise CredentialCorrupt('MCP 凭据明文不是对象')
    return data


def validate_token_endpoint(url: Optional[str], provider: str) -> Optional[str]:
    """刷新端点校验：只允许 https + 该 provider 登记的域名。

    服务端 DCR 元数据里的 endpoint 也走这里 —— 元数据来自外部，
    不校验就等于把 SSRF 开关交给对方。
    """
    if not url:
        return None
    from urllib.parse import urlparse

    parsed = urlparse(url)
    expected = _TOKEN_ENDPOINT_HOSTS.get(provider)
    if parsed.scheme != 'https' or not expected or parsed.hostname != expected:
        # 文案只说"该服务登记不合法"：端点细节属于配置，不该出现在用户可见错误里。
        raise ValueError(f'provider {provider!r} 的授权服务登记不合法')
    return url


def _coerce_user_id(user_id: Any) -> Optional[int]:
    """``resolve_token`` 的历史签名是 ``Optional[str]``；这里把它安全收敛到 int。

    不可解析（例如测试里的 ``'u-1'``）返回 ``None``，调用方据此报「用户尚未连接」，
    绝不退化成「取任意一条」。
    """
    if isinstance(user_id, bool):
        return None
    try:
        value = int(user_id)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _naive_now() -> datetime:
    """东八区 naive —— 与 ``expires_at`` 列同口径（SQLite 不保留时区）。"""
    return now_shanghai().replace(tzinfo=None)


@contextmanager
def _session_for_write() -> Iterator[Any]:
    """写路径的会话：请求内复用 user_session；非请求上下文显式提交。

    ``user_session()`` 在请求上下文里由 teardown 统一提交（#1640），
    在 job / CLI 里只关闭不提交，故这里只在非请求上下文补一次 commit。
    """
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


def save_credential(
    user_id: int,
    provider: str,
    *,
    auth_type: str,
    token: str,
    refresh_token: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    token_endpoint: Optional[str] = None,
) -> UserMcpCredential:
    """按 ``(user_id, provider)`` upsert 一份加密凭据。

    ``auth_type`` 必须是 :data:`AUTH_TYPES` 之一；``static_token`` 不带 refresh / 过期，
    传了也忽略（避免 API Key 被误当成会过期的 OAuth token）。
    """
    if auth_type not in AUTH_TYPES:
        raise ValueError(f'不支持的认证方式 {auth_type!r}（支持：{", ".join(AUTH_TYPES)}）')
    if not token or not token.strip():
        raise ValueError('凭据不能为空')
    if not provider or len(provider) > 50:
        raise ValueError('provider 非法')

    version = current_key_version()
    endpoint = validate_token_endpoint(token_endpoint, provider) if auth_type == 'oauth2' else None
    payload: Dict[str, Any] = {'token': token.strip()}
    cipher = encrypt_payload(payload, version)
    # refresh_token 单独加密：刷新时不必解密 access_token，
    # 也让「只有 access 泄漏」的场景不至于连长期凭据一起丢。
    refresh_cipher = (
        encrypt_payload({'refresh_token': refresh_token}, version) if auth_type == 'oauth2' and refresh_token else None
    )

    with _session_for_write() as db:
        row = (
            db.query(UserMcpCredential)
            .filter(
                and_(
                    UserMcpCredential.user_id == user_id,
                    UserMcpCredential.provider == provider,
                )
            )
            .first()
        )
        if row is None:
            row = UserMcpCredential(user_id=user_id, provider=provider)
            db.add(row)
        row.auth_type = auth_type
        row.cipher_text = cipher
        row.refresh_cipher = refresh_cipher
        row.expires_at = expires_at if auth_type == 'oauth2' else None
        row.token_endpoint = endpoint
        row.key_version = version
        row.status = 'active'
        row.last_refreshed_at = _naive_now() if auth_type == 'oauth2' else None
        row.last_error_kind = None
        db.flush()
        return row


def save_oauth_token(
    user_id: int,
    provider: str,
    *,
    access_token: str,
    refresh_token: Optional[str] = None,
    expires_in: Optional[int] = None,
    token_endpoint: Optional[str] = None,
) -> UserMcpCredential:
    """授权码回调 / 刷新成功后的写入口（S5b 调用）。"""
    expires_at = _naive_now() + timedelta(seconds=expires_in) if expires_in else None
    return save_credential(
        user_id,
        provider,
        auth_type='oauth2',
        token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        token_endpoint=token_endpoint,
    )


def save_static_token(user_id: int, provider: str, api_key: str) -> UserMcpCredential:
    """用户在连接管理页粘贴 API Key 的写入口（无过期、无刷新、无 URL）。"""
    return save_credential(user_id, provider, auth_type='static_token', token=api_key)


def load_credential(user_id: Any, provider: str, allow_expired: bool = False) -> Optional[UserCredential]:
    """按 ``(user_id, provider)`` 读凭据；不存在返回 ``None``。

    过期判定在这里做，但**不自动刷新**——刷新涉及网络调用与 state/锁，
    属于授权编排层（S5b）的职责。这里只把过期事实抛成 ``McpAuthError``，
    让上层决定是刷新还是提示用户重连。
    ``allow_expired=True`` 仅供刷新编排读取 refresh_token：access_token 过期后
    refresh_token 仍然有效，若过期即抛错，刷新链路自己就取不到凭据（死锁）。
    """
    uid = _coerce_user_id(user_id)
    if uid is None or not provider:
        return None
    with user_session() as db:
        row = (
            db.query(UserMcpCredential)
            .filter(
                and_(
                    UserMcpCredential.user_id == uid,
                    UserMcpCredential.provider == provider,
                )
            )
            .first()
        )
        if row is None or row.status != 'active':
            return None
        data = decrypt_payload(row.cipher_text, row.key_version)
        token = data.get('token')
        if not token:
            raise CredentialCorrupt('MCP 凭据缺少 token 字段')

        refresh = data.get('refresh_token')
        if row.refresh_cipher:
            refresh_data = decrypt_payload(row.refresh_cipher, row.key_version)
            refresh = refresh_data.get('refresh_token')

        if row.expires_at and row.expires_at <= _naive_now() and not allow_expired:
            raise McpAuthError('授权已过期，请重新连接', provider=provider)

        return UserCredential(
            provider=row.provider,
            auth_type=row.auth_type,
            token=token,
            refresh_token=refresh,
            expires_at=row.expires_at,
            token_endpoint=row.token_endpoint,
            key_version=row.key_version,
        )


def user_token(user_id: Any, provider: str) -> str:
    """``resolve_token`` 的用户私有分支唯一入口（保持 credentials.py 轻薄）。

    无凭据 / 非活跃 → 直接抛 ``McpUserTokenMissing``。异常类型在凭据路由层定义，
    但「缺用户凭据」这个判断必须和「查表解密」待在一起，否则调用方会各自写一遍
    ``if not token``，其中一处漏了就退化成空字符串继续调用上游。
    """
    cred = load_credential(user_id, provider)
    if cred is None:
        raise McpUserTokenMissing('用户尚未连接该服务', provider=provider)
    return cred.token


def delete_credential(user_id: int, provider: str) -> bool:
    """断开连接：物理删除（不留 revoked 残行，避免管理页出现幽灵连接）。"""
    with _session_for_write() as db:
        deleted = (
            db.query(UserMcpCredential)
            .filter(
                and_(
                    UserMcpCredential.user_id == user_id,
                    UserMcpCredential.provider == provider,
                )
            )
            .delete(synchronize_session=False)
        )
        return bool(deleted)


def list_connections(user_id: int) -> list[Dict[str, Any]]:
    """连接管理页列表：**只返回可展示字段**，绝不返回密文 / token。"""
    with user_session() as db:
        rows = (
            db.query(UserMcpCredential)
            .filter(UserMcpCredential.user_id == user_id)
            .order_by(UserMcpCredential.provider)
            .all()
        )
        return [
            {
                'provider': row.provider,
                'auth_type': row.auth_type,
                'status': row.status,
                'expires_at': row.expires_at.isoformat() if row.expires_at else None,
                'updated_at': row.updated_at.isoformat() if row.updated_at else None,
                'last_error_kind': row.last_error_kind,
                'key_version': row.key_version,
            }
            for row in rows
        ]


def pkce_pair() -> Tuple[str, str]:
    """生成 PKCE verifier / S256 challenge（授权编排层调用）。"""
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')
    return verifier, challenge

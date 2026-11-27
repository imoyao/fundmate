# -*- coding: utf-8 -*-
"""用户私有 MCP 凭据表（S5，多用户隔离）。

设计文档 ``docs/dev/mcp-connection-management.md`` §2.1。一条记录 = 一个用户
对一家 MCP 服务的**一份**凭据，按 ``user_id`` 隔离，``family_id`` 不参与
（授权是个人行为；与 ``UserPreference`` 同口径）。

同一张表承载两种连接方式：

- ``auth_type='oauth2'``：浏览器跳转授权码流程拿到的 access_token，
  可带 refresh_token / 过期时间 / 刷新端点；
- ``auth_type='static_token'``：用户在连接管理页粘贴的 API Key，
  无过期时间、无刷新端点。

**表里没有 url 列**：服务地址只能在 provider 注册表里由代码登记，
用户自带地址会打开 SSRF 面（见设计文档 §7）。

数据域：``user``（含 user_id），登记见 ``app.core.db_factory.DATA_DOMAIN_REGISTRY``。
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class UserMcpCredential(Base, PrimaryKeyMixin, TimestampMixin):
    """一个用户对一个 provider 的加密凭据。"""

    __tablename__ = 'user_mcp_credentials'
    __table_args__ = (UniqueConstraint('user_id', 'provider', name='uq_user_mcp_user_provider'),)

    #: 归属用户（多用户隔离键；与 family 无关）
    user_id = Column(
        Integer,
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='归属用户（多用户隔离键）',
    )
    #: provider 注册表键（不是 MCP 地址）
    provider = Column(String(50), nullable=False, comment='MCP provider 名')
    #: oauth2（浏览器授权） / static_token（用户粘贴 API Key）
    auth_type = Column(String(20), nullable=False, default='oauth2', comment='认证方式')

    #: Fernet 加密的凭据 JSON；明文只在内存中存在
    cipher_text = Column(Text, nullable=False, comment='Fernet 加密的凭据 JSON')
    #: Fernet 加密的 refresh_token（仅 oauth2）
    refresh_cipher = Column(Text, nullable=True, comment='Fernet 加密的 refresh_token')
    #: 过期时间（东八区 naive）；空表示不过期
    expires_at = Column(DateTime, nullable=True, comment='过期时间；空表示不过期')
    #: 刷新端点；只允许 https + provider 白名单域名
    token_endpoint = Column(String(500), nullable=True, comment='OAuth 刷新端点（白名单 https）')
    #: 加密密钥版本，支持轮换
    key_version = Column(Integer, nullable=False, default=1, comment='加密密钥版本')

    status = Column(String(20), nullable=False, default='active', comment='active / expired / revoked')
    last_refreshed_at = Column(DateTime, nullable=True, comment='最近一次刷新时间')
    #: 对应 McpErrorKind；绝不存 token / 报文原文
    last_error_kind = Column(String(40), nullable=True, comment='最近一次失败种类（不存明文）')

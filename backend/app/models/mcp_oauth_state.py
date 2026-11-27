# -*- coding: utf-8 -*-
"""OAuth 授权码流程的一次性 state（S5b）。

为什么落库而不是放进 session / 内存：

- OAuth 回调是**浏览器独立请求**，不携带 JWT；state 是唯一能证明
  "这次回调属于哪个用户、哪次授权"的凭据，必须能跨请求、跨进程读；
- 一次性消费要求有原子判据（``used_at``），内存 dict 在服务重启 /
  多 worker 下会失效或被绕过；
- PKCE verifier 属于短期密钥，存密文而不是明文（与
  ``user_mcp_credentials`` 同一套 Fernet 密钥）。

数据域：``user``（含 user_id），登记见 ``app.core.db_factory.DATA_DOMAIN_REGISTRY``。
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class McpOAuthState(Base, PrimaryKeyMixin, TimestampMixin):
    """一次授权尝试；回调成功后 ``used_at`` 置位，永不复用。"""

    __tablename__ = 'mcp_oauth_states'

    #: 回调带来的随机 state（32 字节 URL-safe，唯一约束兜底）
    state = Column(String(100), nullable=False, unique=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='发起授权的用户',
    )
    provider = Column(String(50), nullable=False, comment='MCP provider 名')
    #: Fernet 加密的 PKCE verifier（token 交换时才解密）
    verifier_cipher = Column(String(500), nullable=False, comment='加密的 PKCE verifier')
    #: 加密所用密钥版本（轮换期间仍按行内版本解密，与凭据表同口径）
    key_version = Column(Integer, nullable=False, default=1, comment='加密密钥版本')
    #: 过期时间（东八区 naive）
    expires_at = Column(DateTime, nullable=False, index=True)
    #: 一次性消费标记；非空即拒绝再次使用
    used_at = Column(DateTime, nullable=True)

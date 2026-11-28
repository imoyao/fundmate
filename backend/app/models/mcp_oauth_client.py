# -*- coding: utf-8 -*-
"""OAuth provider 的 DCR 注册结果（client_id 持久化）。

为什么落库而不是只放在进程内存：

- DCR 的 ``client_id`` 是 refresh_token 的**绑定对象**（``token_endpoint_auth_method=none``
  的客户端，刷新请求必须携带原 client_id）。进程重启后若重新注册拿到新 id，
  存量用户的 refresh_token 会全部失效 ⇒ 每次发版都强制全体用户重连；
- 同 provider 只注册一次也避免向上游累积一次性注册垃圾。

``client_id`` 不是机密（授权服务器按它做资源标识），明文存储；若未来某
provider 返回 ``client_secret``，届时再加密落列——按需存，不预堆字段。

数据域：``user``（与 OAuth 编排同域），登记见 ``app.core.db_factory.DATA_DOMAIN_REGISTRY``。
"""

from sqlalchemy import Column, DateTime, String

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin
from app.core.time_utils import now_shanghai


class McpOAuthClient(Base, PrimaryKeyMixin, TimestampMixin):
    """一行 = 一个 provider 的 DCR 注册结果；``provider`` 唯一约束兜并发竞态。"""

    __tablename__ = 'mcp_oauth_clients'

    provider = Column(String(50), nullable=False, unique=True, index=True, comment='MCP provider 名')
    client_id = Column(String(255), nullable=False, comment='DCR 签发的客户端标识')
    #: 注册完成时间（东八区 naive）；排查「为什么换 id」时对照上游注册记录
    registered_at = Column(
        DateTime,
        nullable=False,
        default=lambda: now_shanghai().replace(tzinfo=None),
    )

# -*- coding: utf-8 -*-
"""MCP 工具目录（tools/list 采样结果的持久化）。

为什么落库而不是只随 verify 响应回显：

- 连接校验（S5f）的工具清单只活在响应里，页面一刷新就没了；
  「上游能干什么」是连接管理页的常驻信息，也是能力高亮与后续对账的底稿；
- 工具清单是**服务的属性**，不是用户数据 —— 与 ``mcp_oauth_clients`` 同理
  无 ``user_id``，任何用户 verify 成功都会刷新这份 provider 级缓存。

``description`` 存上游原文（不翻译不改写）；上游下线的工具在下次全量对齐时删除。
数据域：``user``（与 OAuth 编排同域），登记见 ``app.core.db_factory.DATA_DOMAIN_REGISTRY``。
"""

from sqlalchemy import Column, DateTime, String, Text, UniqueConstraint

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin
from app.core.time_utils import now_shanghai


class McpProviderTool(Base, PrimaryKeyMixin, TimestampMixin):
    """一行 = 某个 provider 上游真实存在的一个工具。"""

    __tablename__ = 'mcp_provider_tools'
    __table_args__ = (UniqueConstraint('provider', 'tool_name', name='uq_mcp_tool_provider_name'),)

    provider = Column(String(50), nullable=False, index=True, comment='MCP provider 名')
    tool_name = Column(String(100), nullable=False, comment='上游 tools/list 里的工具名')
    description = Column(Text, nullable=False, default='', comment='上游描述原文')
    #: 最近一次采样时间（东八区 naive）；判断目录新鲜度用
    fetched_at = Column(
        DateTime,
        nullable=False,
        default=lambda: now_shanghai().replace(tzinfo=None),
    )

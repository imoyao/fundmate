# -*- coding: utf-8 -*-
"""数据同步审计表（#3304）：每次同步尝试一行，事后可追溯污染来源。

为什么独立成表而不复用 ``mcp_call_logs``：调用日志回答「这次 HTTP 烧了谁的额度」，
一行 = 一次能力调用；同步审计回答「**用户确认了什么**」——用了哪几个账户、
置信度判成什么级、低置信时是不是被用户强制导入。判定与人的决策都在这一层，
写进调用日志会把它埋进 HTTP 细节里。

``payload`` 存同步返回的**结构化快照**（截断）：v1 同步不直接写持仓/流水
（份额完整性约束 #3135 要求成对的流水，直接造 Position 会破坏不变量），
先把上游原始结构与用户决策留痕，真实写账本通道另开卡。

数据域：``user``（含 user_id），登记见 ``app.core.db_factory.DATA_DOMAIN_REGISTRY``。
"""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin

#: 置信度等级（conf.high / conf.low / conf.error）
CONFIDENCE_LEVELS = ('high', 'low', 'error')
#: 快照截断上限：正常持仓返回几十 KB，防异常超大报文撑爆行
PAYLOAD_MAX_CHARS = 100_000


class McpSyncAudit(Base, PrimaryKeyMixin, TimestampMixin):
    """一行 = 用户发起的一次数据同步尝试（含被拦截的）。"""

    __tablename__ = 'mcp_sync_audits'

    user_id = Column(
        Integer,
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='发起同步的用户（多用户隔离键）',
    )
    provider = Column(String(50), nullable=False, comment='MCP provider 名')
    tool = Column(String(100), nullable=False, comment='同步调用的上游工具名')
    #: 所选账户 [{group, id, name}] 的 JSON（组名是上游五组键，不是本地概念）
    accounts_json = Column(Text, nullable=False, default='[]', comment='所选账户 JSON')
    #: high / low / error（error = 上游异常，isError / 非 JSON）
    confidence = Column(String(10), nullable=False, comment='置信度等级')
    #: 判定理由（中文，可直接展示）的 JSON 数组
    reasons_json = Column(Text, nullable=False, default='[]', comment='判定理由 JSON')
    #: 低置信且用户仍确认导入（强制标志，污染溯源的关键位）
    forced = Column(Boolean, nullable=False, default=False, comment='低置信强制导入')
    #: 是否确认导入（high 自动导入；low 只有 force=True 才为真；error 恒 False）
    imported = Column(Boolean, nullable=False, default=False, comment='是否确认导入')
    #: 上游返回的结构化快照（截断到 PAYLOAD_MAX_CHARS）；调用失败时为空
    payload = Column(Text, nullable=True, comment='上游返回快照（截断）')

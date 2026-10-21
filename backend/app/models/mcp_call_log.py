# -*- coding: utf-8 -*-
"""MCP 调用审计表（S2）。

为什么落库而不是只打日志：设计文档 §5.3 的五段上报链里，「health 能回答这家服务今天
是不是挂了 / 额度用尽」必须有一个**可回读**的事实来源；日志文件在容器里随重启消失，
而 ``sync_logs`` 的粒度是「一个 job 一条」，回答不了「哪一次 MCP 调用、哪一类失败」。

**不落任何凭据与报文原文**：``message`` 只存已脱敏的中文人话（见
``app.services.mcp.errors.sanitize``），上游细节进 ``error_kind`` + ``http_status``。

数据域：``market``（系统级同步审计，与 ``sync_logs`` 同域、同写方），登记见
``app.core.db_factory.DATA_DOMAIN_REGISTRY``。
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.core.database import Base, PrimaryKeyMixin


class McpCallLog(Base, PrimaryKeyMixin):
    """一次 MCP 工具调用（成功 / 失败各一行）。"""

    __tablename__ = 'mcp_call_logs'

    #: 服务标识（``qieman`` / ``wind``），与 provider 注册表键一致
    provider = Column(String(30), nullable=False, index=True)
    #: 能力名（``strategy_composition`` 等），不是上游工具名 —— 工具名会变，能力名稳定
    capability = Column(String(60), nullable=False)
    #: 数据归属（``public_market`` / ``platform_public`` / ``user_private``）
    scope = Column(String(20), nullable=True)
    #: 是否成功
    ok = Column(Boolean, nullable=False, default=True)
    #: 失败种类（``McpErrorKind`` 的值；成功为 NULL）
    error_kind = Column(String(20), nullable=True)
    #: HTTP 状态码（有语义时记录；S3 采样 Wind 真实报文的依据）
    http_status = Column(Integer, nullable=True)
    #: 调用耗时（毫秒）
    duration_ms = Column(Integer, nullable=True)
    #: 已脱敏的中文人话（与 ``McpError.user_message`` 同源）
    message = Column(String(300), nullable=True)
    #: 调用发生时间（东八区墙钟，naive —— 与 ``sync_logs.started_at`` 同口径）
    called_at = Column(DateTime, nullable=False, index=True)

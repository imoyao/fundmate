# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/9/26
# File : schemas.py
"""账本精灵对话请求 schema（#1121 S1；S2 演进为服务端权威会话）."""

from typing import Optional

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    """POST /api/agent/chat/ 请求体（S2：状态服务端持有，客户端只回传会话 id）.

    session_id 缺省 → 服务端生成新会话；提供但不存在 / 不属于当前用户 → 404
    （越权口径见 session_store.load_or_create）。旧字段（如 session_state）由
    pydantic 默认忽略，旧客户端平滑过渡；白名单校验（G3）仍在
    ``agent_loop.validate_session_state``，本层只做形状约束，避免两套规则漂移。
    """

    message: str = Field(..., description='本轮用户输入')
    session_id: Optional[str] = Field(default=None, description='会话 id（服务端生成；首轮不传，之后回带响应值）')
    goal: Optional[str] = Field(default=None, description='分析目标（仅新建会话时生效），缺省用默认目标')

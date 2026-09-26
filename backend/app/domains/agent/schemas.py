# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/9/26
# File : schemas.py
"""账本精灵对话请求 schema（#1121 S1）."""

from typing import Optional

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    """POST /api/agent/chat/ 请求体。

    session_state 由前端持有、每轮回传；白名单校验（G3）在
    ``agent_loop.validate_session_state`` 统一执行，本层只做形状约束，
    避免两套校验规则漂移。
    """

    message: str = Field(..., description='本轮用户输入')
    session_id: str = Field(..., description='会话 id（前端生成，轮次闸按 user_id+session_id 计数）')
    session_state: Optional[dict] = Field(default=None, description='上一轮回传的会话状态，首轮不传')
    goal: Optional[str] = Field(default=None, description='分析目标，缺省用默认目标')

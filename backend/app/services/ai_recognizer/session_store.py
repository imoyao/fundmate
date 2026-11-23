# -*- coding: utf-8 -*-
"""账本精灵会话存取（#1121 S2）：服务端权威 session 的加载 / 创建 / 归属校验.

职责边界：
- 只做「行级」读写与归属校验，不做 prompt 组装 / 压缩（那是 agent_loop 的事）；
- 列表 / 搜索 / 标题派生属于**读路径**，已下沉到 ``session_list``；本模块 re-export，
  调用点（views / 脚本 / 测试）不必集体改 import；
- 标题只在**新建会话**时固化成 ``title``（首条用户输入）。存量会话不重写：它的首条输入
  可能已被压缩裁剪，用当前这轮覆盖只会得到错标题——存量回填归
  ``core/migrations_agent.py``；
- 会话含 user_id → user 域，经 database.user_session() 的请求级会话——
  提交由 teardown_request_session 统一执行（conventions §2.13 方案 A：只 flush 不 commit）。
"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session as OrmSession

from app.core.exceptions import ErrorCode, SBException
from app.domains.agent.models import AgentSession
from app.services.ai_recognizer.session_list import (
    PREVIEW_CAP,
    derive_title,
    iso_or_none,
    list_sessions,
    to_list_item,
)

DEFAULT_GOAL = '分析账户收益'

__all__ = [
    'DEFAULT_GOAL',
    'PREVIEW_CAP',
    'get_owned',
    'list_sessions',
    'load_or_create',
    'to_detail',
    'to_list_item',
]


def get_owned(db: OrmSession, *, session_id: str, user_id: int) -> AgentSession:
    """按 session_id 取**归属当前用户**的会话行，越权 / 不存在一律 404.

    越权口径（P4 修复）：session_id 不存在、或不属于当前 user_id，一律 404
    RESOURCE_NOT_FOUND——403 会泄露「该 id 存在」，与 get_owned_or_404 一致。
    session_id 由服务端 uuid4 生成，前端无法预测 / 伪造他人会话。
    """
    row = db.query(AgentSession).filter(AgentSession.session_id == session_id).first()
    if row is None or row.user_id != user_id:
        raise SBException(ErrorCode.RESOURCE_NOT_FOUND.code, '会话不存在或已过期', 404)
    return row


def load_or_create(
    db: OrmSession,
    *,
    session_id: Optional[str],
    user_id: int,
    goal: Optional[str] = None,
    first_message: Optional[str] = None,
) -> AgentSession:
    """按 session_id 加载会话，缺省则新建；返回**归属当前用户**的会话行（first_message 只在新建时固化 title）."""
    if session_id:
        return get_owned(db, session_id=session_id, user_id=user_id)

    row = AgentSession(
        session_id=str(uuid.uuid4()),
        user_id=user_id,
        goal=goal or DEFAULT_GOAL,
        title=derive_title(first_message),
    )
    db.add(row)
    db.flush()  # 让 session_id/主键立即可见；commit 留给请求边界（§2.13）
    return row


def to_detail(row: AgentSession) -> dict:
    """单会话详情（#1719 回放）：含 messages 全量原文（本就是回放对象，不分页）."""
    return {
        'session_id': row.session_id,
        'title': row.title or '',
        'goal': row.goal,
        'turn_count': row.turn_count,
        'created_at': iso_or_none(row.created_at),
        'updated_at': iso_or_none(row.updated_at),
        'messages': list(row.messages or []),
    }

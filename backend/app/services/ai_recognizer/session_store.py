# -*- coding: utf-8 -*-
"""账本精灵会话存取（#1121 S2）：服务端权威 session 的加载 / 创建 / 归属校验.

职责边界：
- 只做「行级」读写与归属校验，不做 prompt 组装 / 压缩（那是 agent_loop 的事）；
- 会话含 user_id → user 域，经 database.user_session() 的请求级会话——
  提交由 teardown_request_session 统一执行（conventions §2.13 方案 A：只 flush 不 commit）。
"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session as OrmSession

from app.core.exceptions import ErrorCode, SBException
from app.domains.agent.models import AgentSession

DEFAULT_GOAL = '分析账户收益'


def load_or_create(
    db: OrmSession,
    *,
    session_id: Optional[str],
    user_id: int,
    goal: Optional[str] = None,
) -> AgentSession:
    """按 session_id 加载会话，缺省则新建；返回**归属当前用户**的会话行.

    越权口径（P4 修复）：session_id 不存在、或不属于当前 user_id，一律 404
    RESOURCE_NOT_FOUND——403 会泄露「该 id 存在」，与 get_owned_or_404 一致。
    session_id 由服务端 uuid4 生成，前端无法预测 / 伪造他人会话。
    只 flush 不 commit：HTTP 路径由请求 teardown 统一提交。
    """
    if session_id:
        row = db.query(AgentSession).filter(AgentSession.session_id == session_id).first()
        if row is None or row.user_id != user_id:
            raise SBException(ErrorCode.RESOURCE_NOT_FOUND.code, '会话不存在或已过期', 404)
        return row

    row = AgentSession(
        session_id=str(uuid.uuid4()),
        user_id=user_id,
        goal=goal or DEFAULT_GOAL,
    )
    db.add(row)
    db.flush()  # 让 session_id/主键立即可见；commit 留给请求边界（§2.13）
    return row

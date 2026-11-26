# -*- coding: utf-8 -*-
"""账本精灵会话删除（2026-11 用户反馈「历史记录无法删除」）.

独立成模块而不是加进 ``session_store``：那个文件已触到「services 层只减不增」
的体量基线（scripts/guard_service_size.py），而删除是**写路径**——读 / 写分家也
比把两种职责塞在一个模块里清楚。归属校验仍复用 ``session_store.get_owned``，
越权口径只有一处定义。

语义边界：
- **硬删除**：agent_session 没有 is_deleted 列。加软删要同时改读路径三处
  （list / detail / load_or_create），还会让 404 的语义变模糊（存在但不可见）。
- **trace 一并删除**：agent_trace 按 session_id 冗余关联（刻意无 SQL FK），
  留下会变成无法归属的孤儿行；且 trace 里含工具参数（已脱敏）——用户说
  「删掉这条记录」指的是这条会话的全部痕迹，只删列表那一行等于留了一半。
- **只 flush 不 commit**：提交由请求边界统一执行（conventions §2.13）。
"""

from sqlalchemy.orm import Session as OrmSession

from app.domains.agent.models import AgentTrace
from app.services.ai_recognizer.session_store import get_owned

__all__ = ['delete_owned']


def delete_owned(db: OrmSession, *, session_id: str, user_id: int) -> None:
    """删除归属当前用户的会话及其决策 trace（不存在 / 他人会话一律 404）."""
    row = get_owned(db, session_id=session_id, user_id=user_id)
    db.query(AgentTrace).filter(AgentTrace.session_id == session_id).delete(synchronize_session=False)
    db.delete(row)
    db.flush()

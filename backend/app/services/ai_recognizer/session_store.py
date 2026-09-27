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
from app.core.utils import paginate
from app.domains.agent.models import AgentSession

DEFAULT_GOAL = '分析账户收益'

# 历史栏预览截断（#1719）：列表页只回「最后一条用户输入」的一小段，
# 绝不整列回传 messages——列表是读路径，行体积必须与会话长度无关。
PREVIEW_CAP = 60


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
) -> AgentSession:
    """按 session_id 加载会话，缺省则新建；返回**归属当前用户**的会话行.

    只 flush 不 commit：HTTP 路径由请求 teardown 统一提交（§2.13）。
    加载分支即 get_owned（#1719 抽出复用，404 口径两处同源）。
    """
    if session_id:
        return get_owned(db, session_id=session_id, user_id=user_id)

    row = AgentSession(
        session_id=str(uuid.uuid4()),
        user_id=user_id,
        goal=goal or DEFAULT_GOAL,
    )
    db.add(row)
    db.flush()  # 让 session_id/主键立即可见；commit 留给请求边界（§2.13）
    return row


def _preview(messages) -> str:
    """历史栏预览：取**最后一条**用户输入（空轮跳过，向前找）。"""
    for turn in reversed(list(messages or [])):
        text = str((turn or {}).get('user') or '').strip()
        if text:
            return text[:PREVIEW_CAP]
    return ''


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def to_list_item(row: AgentSession) -> dict:
    """列表项（#1719）：只带渲染历史栏所需的字段。

    goal 是**会话展示标题**（缺省值统一为 DEFAULT_GOAL，#1718 已确认它不是分析约束），
    故另给 preview——否则历史栏每一行都是同一个标题，无法辨认。
    preview 为读时派生（从 messages 取末条用户输入），**零新增列**。
    """
    return {
        'session_id': row.session_id,
        'goal': row.goal,
        'preview': _preview(row.messages),
        'turn_count': row.turn_count,
        'created_at': _iso(row.created_at),
        'updated_at': _iso(row.updated_at),
    }


def to_detail(row: AgentSession) -> dict:
    """单会话详情（#1719 回放）：含 messages 全量原文（本就是回放对象，不分页）。"""
    return {
        'session_id': row.session_id,
        'goal': row.goal,
        'turn_count': row.turn_count,
        'created_at': _iso(row.created_at),
        'updated_at': _iso(row.updated_at),
        'messages': list(row.messages or []),
    }


def list_sessions(
    db: OrmSession,
    *,
    user_id: int,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """本人历史会话列表（#1719 读路径）：按更新时间倒序 + 分页。

    - 只读已存在的 agent_session 表：零新增表 / 列 / 抓取（数据准入四问见 PR）；
    - 按 user_id 过滤走索引（models.user_id index=True），禁止无条件全表扫描；
    - 跨用户天然不可见（filter 在 user_id 上），不依赖调用方过滤。
    """
    query = (
        db.query(AgentSession)
        .filter(AgentSession.user_id == user_id)
        .order_by(AgentSession.updated_at.desc(), AgentSession.id.desc())
    )
    rows, total = paginate(query, page=page, per_page=per_page)
    return [to_list_item(r) for r in rows], total

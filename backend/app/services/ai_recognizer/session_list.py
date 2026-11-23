# -*- coding: utf-8 -*-
"""会话列表读路径：标题派生 + 关键词搜索（#1719 历史栏的检索扩展）.

职责边界
--------
只回答「列表怎么查、怎么显示」。归属校验在 ``session_store.get_owned``，
写入在 ``session_store.load_or_create`` —— 本模块不碰这两件事。

为什么标题要落库、预览不落库
----------------------------
- 预览取「末条用户输入」：``messages`` 只保留最近 12 条（``agent_loop`` 硬截断），
  末条永远在，读时派生即可 → 零新增列（#1719 的既有取舍，保留）；
- 标题必须取「首条用户输入」，而 ``messages`` 会被压缩裁剪到最近 3 轮
  （``agent_loop._maybe_compress``）。读时再取 ``messages[0]`` 会随会话变长**漂移**成
  中途某句话，并且越来越像预览——所以标题在**创建时**固化进 ``title`` 列
  （加列迁移见 ``core/migrations_agent.py``）。这是本次唯一新增的列。

搜索口径（v1：只搜标题）
------------------------
- 不搜 ``messages``：该列是 JSON，中文落库是 ``\\u6e29\\u5ea6`` 形态（SQLite 侧
  ``json.dumps`` 用 ``ensure_ascii=True``），``LIKE '%温度%'`` **永远 0 命中**。
  「看起来实现了搜索、其实一次都不会命中」比没有搜索更坏。正文检索要独立索引
  （FTS5 / embedding），另开卡；
- 不搜 ``goal``：缺省值恒为 ``DEFAULT_GOAL``（前端从未传过自定义目标），把它纳入会让
  「收益」「分析」这类高频词命中全部会话，把搜索变成噪声源；
- 通配符必须转义：不转义时 ``q='%'`` 命中全部、``q='_'`` 命中任意单字。
"""

from typing import Optional

from sqlalchemy.orm import Query
from sqlalchemy.orm import Session as OrmSession

from app.core.utils import paginate
from app.domains.agent.models import AgentSession

# 标题展示上限（列宽 60，留余量给侧栏单行省略）
TITLE_CAP = 40
# 历史栏预览截断（#1719）：列表页只回「最后一条用户输入」的一小段，
# 绝不整列回传 messages——列表是读路径，行体积必须与会话长度无关。
PREVIEW_CAP = 60
# 关键词上限：查询串再长也只是噪声，截断而非报错（前端输入框不设硬限制）
KEYWORD_CAP = 40


def _squash(text) -> str:
    """压掉换行与连续空白：标题是单行展示，换行会把列表行高撑开."""
    return ' '.join(str(text or '').split())


def derive_title(message) -> str:
    """首条用户输入 → 会话标题（单行、去空白、截断）."""
    return _squash(message)[:TITLE_CAP]


def _preview(messages) -> str:
    """历史栏预览：取**最后一条**用户输入（空轮跳过，向前找）."""
    for turn in reversed(list(messages or [])):
        text = str((turn or {}).get('user') or '').strip()
        if text:
            return text[:PREVIEW_CAP]
    return ''


def _escape_like(keyword: str) -> str:
    """转义 LIKE 通配符（反斜杠必须先转，否则会二次转义自己的转义符）."""
    return keyword.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def keyword_pattern(keyword) -> Optional[str]:
    """关键词 → LIKE 模式；空 / 纯空白 → None（调用方据此跳过过滤）."""
    kw = _squash(keyword)[:KEYWORD_CAP]
    return f'%{_escape_like(kw)}%' if kw else None


def to_list_item(row: AgentSession) -> dict:
    """列表项（#1719）：只带渲染历史栏所需的字段.

    title 为创建时固化的标题；存量行由迁移回填，仍为空时前端显示「未命名会话」。
    preview 为读时派生（从 messages 取末条用户输入），零新增列。
    """
    return {
        'session_id': row.session_id,
        'title': row.title or '',
        'goal': row.goal,
        'preview': _preview(row.messages),
        'turn_count': row.turn_count,
        'created_at': iso_or_none(row.created_at),
        'updated_at': iso_or_none(row.updated_at),
    }


def iso_or_none(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def list_sessions(
    db: OrmSession,
    *,
    user_id: int,
    keyword: str = '',
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """本人历史会话列表（#1719 读路径）：按更新时间倒序 + 分页 + 可选标题检索.

    - 只读已存在的 agent_session 表：仅新增 title 一列（其余零新增表 / 列）；
    - 按 user_id 过滤走索引（models.user_id index=True），禁止无条件全表扫描；
    - 跨用户天然不可见（filter 在 user_id 上），不依赖调用方过滤——
      关键词过滤必须叠加在这条 filter 之后，绝不能反过来。
    """
    query = db.query(AgentSession).filter(AgentSession.user_id == user_id)
    query = _apply_keyword(query, keyword)
    query = query.order_by(AgentSession.updated_at.desc(), AgentSession.id.desc())
    rows, total = paginate(query, page=page, per_page=per_page)
    return [to_list_item(r) for r in rows], total


def _apply_keyword(query: Query, keyword) -> Query:
    """给列表查询叠加标题过滤；空关键词原样返回（不做无意义 where）."""
    pattern = keyword_pattern(keyword)
    if pattern is None:
        return query
    return query.filter(AgentSession.title.like(pattern, escape='\\'))

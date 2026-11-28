# -*- coding: utf-8 -*-
"""MCP 工具目录的库读写（``mcp_provider_tools`` 表，S5g）。

verify（S5f）拿到上游 ``tools/list`` 后把全量清单对齐进库：新增插入、
描述变化的更新、上游已下线的删除 —— **以当次响应为准**，库里永远反映
上游现状，而不是采样历史。读侧（``GET /connections/<provider>/tools/``）
不需要用户在线，从库里返回上次采样的目录即可。

事务边界与 ``oauth_client_store`` 同理：``user_session_factory`` 开独立
短会话，不走请求级 ``user_session`` —— 目录是服务级共享数据，不是请求
工作单元的一部分；verify 的请求会话若混入这批写入，回滚语义会变含混。
"""

from typing import Any, Dict, List

from app.core.db_factory import user_session_factory
from app.core.time_utils import now_shanghai
from app.models.mcp_provider_tool import McpProviderTool


def sync_tools(provider: str, tools: List[Dict[str, Any]]) -> int:
    """全量对齐 provider 的工具目录，返回目录行数。

    ``tools`` 是 ``connection_check.check_connection`` 的归一化输出
    （``[{name, description}]``）。空 provider / 空 name 的条目直接忽略。
    """
    if not provider:
        raise ValueError('provider 不能为空')
    valid = [(str(t['name']), str(t.get('description') or '')) for t in tools if t.get('name')]
    db = user_session_factory()()
    try:
        existing = {
            row.tool_name: row for row in db.query(McpProviderTool).filter(McpProviderTool.provider == provider)
        }
        now = now_shanghai().replace(tzinfo=None)
        for name, desc in valid:
            row = existing.pop(name, None)
            if row is None:
                db.add(McpProviderTool(provider=provider, tool_name=name, description=desc, fetched_at=now))
            elif row.description != desc:
                row.description = desc
                row.fetched_at = now
            else:
                row.fetched_at = now
        # existing 剩下的 = 上游已下线：目录反映现状，不是采样历史
        for stale in existing.values():
            db.delete(stale)
        db.commit()
        return len(valid)
    finally:
        db.close()


def list_tools(provider: str) -> List[Dict[str, Any]]:
    """读目录（按工具名排序）；未采样过返回空列表。"""
    if not provider:
        return []
    db = user_session_factory()()
    try:
        rows = (
            db.query(McpProviderTool)
            .filter(McpProviderTool.provider == provider)
            .order_by(McpProviderTool.tool_name)
            .all()
        )
        return [
            {'name': row.tool_name, 'description': row.description, 'fetched_at': row.fetched_at.isoformat()}
            for row in rows
        ]
    finally:
        db.close()

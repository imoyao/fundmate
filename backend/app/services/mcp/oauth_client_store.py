# -*- coding: utf-8 -*-
"""DCR client_id 的库读写（``mcp_oauth_clients`` 表）。

编排层（``services/mcp/oauth.py``）保持"env 预置 > 库 > DCR"的决策逻辑，
本模块只负责**存取**——把注册结果落库、重启后读回。为什么不直接在编排层
写一行 SQLAlchemy：``mcp_oauth_clients`` 的并发语义（唯一约束兜多进程同时
注册）值得一个有名字、有测试的出口，而不是藏在 ``client_id_for`` 的执行流里。

竞态口径：两个进程同时 DCR 会拿到两个都有效的 client_id（上游不冲突），
落库时唯一约束只让先写者生效，后写者捕获 IntegrityError 后**读回先写者的
值返回**——两个 id 都可用，保留哪个都正确，但库里必须只剩一个真相源。

事务边界：这里用 ``user_session_factory`` 开**独立短会话**，不走请求级
``user_session``——``client_id_for`` 在 ``begin()`` 的请求内被调用，若复用
请求会话，竞态兜底的 ``rollback()`` 会把同一请求里已 flush 的 state 行一并
回滚，授权必然失败。client_id 是服务级数据，不是请求工作单元的一部分。
"""

import logging
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.core.db_factory import user_session_factory
from app.models.mcp_oauth_client import McpOAuthClient

logger = logging.getLogger(__name__)


def read_client_id(provider: str) -> Optional[str]:
    """读 provider 的注册 client_id；未注册返回 ``None``。"""
    if not provider:
        return None
    # user_session_factory 是 sessionmaker 工厂：两次调用得独立短会话（不经请求级共享）。
    db = user_session_factory()()
    try:
        row = db.query(McpOAuthClient).filter(McpOAuthClient.provider == provider).first()
        return row.client_id if row else None
    finally:
        db.close()


def save_client_id(provider: str, client_id: str) -> str:
    """落库注册结果；provider 已有记录时**保留先写者**并返回它的 client_id。

    返回值是"库里最终的 client_id"——调用方必须用它继续授权流程，
    而不是自己刚注册到的那个（竞态下两者可能不同，见模块 docstring）。
    """
    if not provider or not client_id:
        raise ValueError('provider 与 client_id 均不能为空')
    db = user_session_factory()()
    try:
        try:
            db.add(McpOAuthClient(provider=provider, client_id=client_id))
            db.commit()
            return client_id
        except IntegrityError:
            db.rollback()
            existing = db.query(McpOAuthClient).filter(McpOAuthClient.provider == provider).first()
            if existing is None:
                # 唯一约束报了却读不到行：超出本模块可解释的范围，如实抛出。
                raise
            logger.info(f'MCP DCR client_id 并发注册：provider={provider} 保留已有注册')
            return existing.client_id
    finally:
        db.close()

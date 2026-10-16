# -*- coding: utf-8 -*-
"""站内通知 Schema。"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class NotificationOut(BaseModel):
    """站内通知。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    level: str = Field(..., description='P0 强 / P1 中 / P2 弱')
    category: str = Field(..., description='strategy 策略 / watchlist 自选 / system 系统')
    title: str = Field(..., description='消息标题（客观陈述，不含投资建议措辞）')
    body: Optional[str] = Field(None, description='消息正文')
    source_type: str = Field(..., description='产生来源，如 allocation_deviation')
    source_key: Optional[str] = Field(None, description='来源业务键（多为标的代码）')
    is_read: bool
    created_at: Optional[str] = Field(None, description='创建时间（ISO，东八区）')
    read_at: Optional[str] = Field(None, description='已读时间（ISO，东八区）')


class NotificationListOut(BaseModel):
    """通知列表 + 未读数 + 首页横栏候选。"""

    items: list[NotificationOut] = Field(default_factory=list)
    total: int = 0
    unread_count: int = 0
    banner: Optional[NotificationOut] = Field(
        None,
        description='首页横栏候选：当前最高优先级的 1 条未读（P0 优先），无则 None',
    )

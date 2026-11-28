# -*- coding: utf-8 -*-
"""MCP 连接管理请求体（S5c）。

只定义**用户能填的字段**：provider 是代码登记的服务名，绝不接受 URL
（SSRF 红线，见 docs/dev/mcp-connection-management.md §7）。
"""

from typing import List

from pydantic import BaseModel, Field, field_validator


class StaticTokenIn(BaseModel):
    """用户粘贴 API Key（静态凭据型 MCP）。"""

    provider: str = Field(..., min_length=1, max_length=50)
    api_key: str = Field(..., min_length=1, max_length=500)

    @field_validator('provider', 'api_key', mode='before')
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class OAuthBeginIn(BaseModel):
    """发起浏览器授权（OAuth2 授权码型 MCP）。"""

    provider: str = Field(..., min_length=1, max_length=50)

    @field_validator('provider', mode='before')
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SyncAccountIn(BaseModel):
    """同步所选的一个账户：组键 + 账户 id（都来自账户发现的真实返回，不收自由文本）。"""

    group: str = Field(..., min_length=1, max_length=30)
    id: str = Field(..., min_length=1, max_length=100)


class SyncIn(BaseModel):
    """发起数据同步（#3304）。``accounts`` 非空由 pydantic 强制——不选账户在
    请求体校验层就被拒，这是「双层校验」的 API 侧第一层；工具契约错位在服务层拦。"""

    tool: str = Field(..., min_length=1, max_length=100)
    accounts: List[SyncAccountIn] = Field(..., min_length=1)
    force: bool = False

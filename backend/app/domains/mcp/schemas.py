# -*- coding: utf-8 -*-
"""MCP 连接管理请求体（S5c）。

只定义**用户能填的字段**：provider 是代码登记的服务名，绝不接受 URL
（SSRF 红线，见 docs/dev/mcp-connection-management.md §7）。
"""

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

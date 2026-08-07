# -*- coding: utf-8 -*-
"""用户 Schema（多用户身份层）。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class UserOut(BaseModel):
    id: int
    supabase_id: Optional[str] = None
    family_id: int
    username: Optional[str] = None
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    email: Optional[str] = None
    role: str
    is_active: int = 1
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    """个人中心资料更新请求体（PATCH /api/users/me/）。

    三个字段均可选；只更新显式传入的字段，未传则保持不变。用户名做唯一性
    校验（作为登录标识，必须全局唯一，D10）；昵称与头像可随意修改。
    """

    username: Optional[str] = Field(default=None, max_length=50)
    nickname: Optional[str] = Field(default=None, max_length=50)
    avatar: Optional[str] = Field(default=None, max_length=500)

    @field_validator('username', 'nickname')
    @classmethod
    def _strip_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

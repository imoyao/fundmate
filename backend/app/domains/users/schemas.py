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

    # 长度限制与前端一致：用户名（登录标识）5-20；昵称（展示名，无唯一约束）
    # 下限 2——覆盖中文最常见的双字昵称，同时挡住单字误触（行业惯例 1-2，见 decisions.md）
    username: Optional[str] = Field(default=None, min_length=5, max_length=20)
    nickname: Optional[str] = Field(default=None, min_length=2, max_length=16)
    avatar: Optional[str] = Field(default=None, max_length=500)

    # mode='before' 必须先 strip 再走 min_length 校验，否则含空格的短值
    # 会先通过 min_length 再被 strip，绕过长度的最短限制
    @field_validator('username', 'nickname', mode='before')
    @classmethod
    def _strip_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class PreferenceUpsert(BaseModel):
    """偏好写入请求体（PUT /api/users/preferences/<key>/）。

    value 必须是 JSON 对象（dict）：偏好值语义为「结构化配置」，
    裸数组/标量无扩展空间，直接拒收避免调用方各自发明编码。
    """

    value: dict = Field(..., description='偏好值（JSON 对象）')


class PreferenceOut(BaseModel):
    """偏好读出（key + 结构化 value + updated_at，供前端合并策略比较新旧）。"""

    key: str
    value: dict
    updated_at: Optional[datetime] = None

# -*- coding: utf-8 -*-
"""家庭 Schema 与家庭成员档案 Schema（#1173）。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from app.domains.families.models import MEMBER_ROLES


class FamilyCreate(BaseModel):
    name: str


class FamilyOut(BaseModel):
    id: int
    name: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FamilyMemberCreate(BaseModel):
    """新增成员：称谓必填，角色可选（默认 other）。"""

    name: str
    role: str = 'other'

    @field_validator('name')
    @classmethod
    def _check_name(cls, v: str) -> str:
        cleaned = (v or '').strip()
        if not cleaned:
            raise ValueError('成员称谓不能为空')
        if len(cleaned) > 50:
            raise ValueError('成员称谓过长（最多 50 字）')
        return cleaned

    @field_validator('role')
    @classmethod
    def _check_role(cls, v: str) -> str:
        if v not in MEMBER_ROLES:
            raise ValueError(f'成员角色无效（可选：{"/".join(MEMBER_ROLES)}）')
        return v


class FamilyMemberUpdate(BaseModel):
    """改成员：全部可选，只更新显式传入的字段。

    ``user_id`` 用 ``Optional[int]`` 且**允许显式传 None**（解绑账号）；
    服务层靠「是否传了 role/is_active」判断是否更新，避免把 None 当成「清空」。
    """

    name: Optional[str] = None
    role: Optional[str] = None
    user_id: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator('name')
    @classmethod
    def _check_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError('成员称谓不能为空')
        if len(cleaned) > 50:
            raise ValueError('成员称谓过长（最多 50 字）')
        return cleaned

    @field_validator('role')
    @classmethod
    def _check_role(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if v not in MEMBER_ROLES:
            raise ValueError(f'成员角色无效（可选：{"/".join(MEMBER_ROLES)}）')
        return v


class FamilyMemberOut(BaseModel):
    """成员响应体（``ledger_count`` 为该成员名下账户数）。"""

    id: int
    name: str
    role: str
    role_label: str
    user_id: Optional[int] = None
    is_active: bool
    ledger_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

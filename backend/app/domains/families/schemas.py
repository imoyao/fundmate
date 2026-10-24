# -*- coding: utf-8 -*-
"""家庭 Schema。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FamilyCreate(BaseModel):
    name: str


class FamilyOut(BaseModel):
    id: int
    name: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FamilyMemberCreate(BaseModel):
    """邀请成员（#1173）：按邮箱预建本地映射行，待对方首次登录时认领。

    没有 service-role 密钥，后端无法直接创建 Supabase Auth 账号；故「增成员」的
    落地形态是**先建本地行**（`supabase_id` 为空），对方用同一邮箱注册/登录时由
    `UserIdentity.provision` 按邮箱认领该行，从而带着既定角色加入本家庭。
    """

    email: str = Field(description='成员邮箱（与 Supabase Auth 账号邮箱一致，认领凭据）')
    nickname: Optional[str] = Field(None, description='成员昵称，缺省取邮箱前缀')
    role: str = Field('member', description='角色：admin / member / viewer')


class FamilyMemberUpdate(BaseModel):
    """修改成员角色 / 昵称（#1173）。字段缺省即不改动。

    不做「停用」：`users.is_active` 目前**没有任何读侧强制**（鉴权中间件不看它），
    提供一个不生效的开关比不提供更糟——要么先给鉴权加拦截，要么先别暴露。
    """

    role: Optional[str] = Field(None, description='admin / member / viewer')
    nickname: Optional[str] = Field(None, description='成员昵称（家庭内展示名）')

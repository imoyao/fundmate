# -*- coding: utf-8 -*-
"""用户 Schema（多用户身份层）。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


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

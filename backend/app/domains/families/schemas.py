# -*- coding: utf-8 -*-
"""家庭 Schema。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class FamilyCreate(BaseModel):
    name: str


class FamilyOut(BaseModel):
    id: int
    name: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

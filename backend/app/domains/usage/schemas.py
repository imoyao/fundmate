# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/12
# File : schemas.py
"""用量 API 响应 Schema."""

from datetime import date

from pydantic import BaseModel


class UsageOut(BaseModel):
    """单个功能的当日用量快照."""

    feature: str
    used: int
    quota: int
    remaining: int
    period_date: date

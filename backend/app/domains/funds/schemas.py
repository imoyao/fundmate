# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/10 20:04
# File : schemas.py
# backend/app/domains/funds/schemas.py

from datetime import date

from pydantic import BaseModel, Field


class FundNavRequest(BaseModel):
    model_config = {'populate_by_name': True}

    symbols: list[str] = Field(..., min_length=1, description='基金代码列表，非空数组')
    target_date: date = Field(..., alias='date', description='净值日期，格式 YYYY-MM-DD')

# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 21:47
# File : utils.py
# app/core/utils.py

"""通用工具函数，如分页等。"""

import datetime
from datetime import date
from functools import wraps
from typing import Any, List, Tuple

from chinese_calendar import find_workday
from flask import jsonify
from sqlalchemy.orm import Query

from app.core.database import get_db


def api_response(data=None, message='ok', total=None):
    """统一 JSON 响应格式."""
    resp = {'data': data, 'message': message}
    if total is not None:
        resp['total'] = total
    return jsonify(resp)


def with_db(func):
    """装饰器：自动注入数据库会话并返回统一格式."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        with get_db() as db:
            return func(db, *args, **kwargs)

    return wrapper


def paginate(query: Query, page: int = 1, per_page: int = 20) -> Tuple[List[Any], int]:
    """
    对查询进行分页，返回 (items, total)。
    page 从 1 开始，per_page 默认 20。
    """
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, total


def get_confirm_date(purchase_date: date, fund_type: str = 'domestic', is_after_15: bool = False) -> date:
    """
    计算场外基金确认日。

    Args:
        purchase_date: 购买日（T日）
        fund_type: 基金类型，'domestic'（普通场外基金）或 'qdii'（QDII基金）
        is_after_15: 是否在15:00之后下单，若为True则T日顺延一个工作日

    Returns:
        确认日（净值确认日期）
    """
    # 如果15:00之后下单，T日顺延一个工作日
    if is_after_15:
        purchase_date = find_workday(delta_days=1, date=purchase_date)

    # QDII基金 T+2，普通基金 T+1
    delta_days = 2 if fund_type == 'qdii' else 1

    return find_workday(delta_days=delta_days, date=purchase_date)


if __name__ == '__main__':
    date = get_confirm_date(datetime.date(2026, 5, 1))
    print(date)

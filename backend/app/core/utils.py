# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 21:47
# File : utils.py
# app/core/utils.py

"""通用工具函数，如分页等。"""

from functools import wraps
from typing import Any, List, Tuple

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

# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/10 21:47
# File : utils.py
# app/core/utils.py

"""通用工具函数，如分页等。"""

from typing import Any, List, Tuple

from sqlalchemy.orm import Query


def paginate(query: Query, page: int = 1, per_page: int = 20) -> Tuple[List[Any], int]:
    """
    对查询进行分页，返回 (items, total)。
    page 从 1 开始，per_page 默认 20。
    """
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, total

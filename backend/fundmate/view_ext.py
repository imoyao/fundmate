#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/5/24 15:19
"""
将view 公用提出来
"""
from flask_sqlalchemy import Pagination

from apiflask.types import PaginationType


class CustomPaginationType(PaginationType, Pagination):
    """
    自定义的type，继承两个类
    """
    pass


def paginate_query(cls, query_args: dict) -> CustomPaginationType:
    """
    分页器
    """
    pagination = cls.query.paginate(page=query_args['page'], per_page=query_args['per_page'])
    return pagination

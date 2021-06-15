#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/5/24 15:19
"""
将view 公用提出来
"""
from apiflask import pagination_builder


def paginate_query(cls, query_args: dict) -> dict:
    pagination = cls.query.paginate(
        page=query_args['page'],
        per_page=query_args['per_page']
    )
    _items = pagination.items
    return {
        'items': _items,
        'pagination': pagination_builder(pagination)
    }

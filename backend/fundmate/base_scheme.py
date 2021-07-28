#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/23 14:06
"""
公用scheme提出来
"""
from apiflask import Schema
from apiflask.fields import Integer
from apiflask.validators import Range


class PaginationSchema(Schema):
    """
    分页请求参数
    """
    page = Integer(missing=1)
    per_page = Integer(missing=20, validate=Range(max=30))


class EmptySchema(Schema):
    pass

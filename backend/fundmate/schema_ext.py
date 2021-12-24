#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/5/24 15:19
"""
公用schema提取
"""
from apiflask import Schema
from apiflask.fields import Integer
from apiflask.validators import Range


class EmptySchema(Schema):
    pass


class CustomPaginationSchema(Schema):
    page = Integer(load_default=1)
    per_page = Integer(load_default=20, validate=Range(max=30))

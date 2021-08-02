#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/27 18:08
"""
类比DRF中的serializer
"""
from apiflask import Schema
from apiflask.fields import Boolean, Dict


class ThermometerInSchema(Schema):
    is_full = Boolean(default=False)


class ThermometerOutSchema(Schema):
    """
    目前支持有知有行、集思录、蛋卷、韭圈儿信息
    """
    yzyx = Dict()
    jsl = Dict()
    dj = Dict()
    jq = Dict()

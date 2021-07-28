#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/27 18:08
"""
类比DRF中的serializer
"""
from apiflask import Schema
from apiflask.fields import String


class CreateAccountSchema(Schema):
    """
    账本创建
    """
    '''
    有知有行：名称、预期年化、投资时间、币种
    '''
    name = String()
    desc = String()


class AccountOutSchema(Schema):
    """
    账号输入
    """
    name = String()
    desc = String()

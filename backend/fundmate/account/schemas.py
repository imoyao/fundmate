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
    各家解决方案：
    有知有行：名称、预期年化、投资时间、币种
    投资账本： 名称
    韭圈儿： 名称
    '''
    name = String()
    desc = String()
    # risk_type =


class AddAccountItemSchema(Schema):
    """
    创建账号后添加购买品种
    韭圈儿：购买平台，基金名称，持有金额，持有收益
    """
    pass


class AccountOutSchema(Schema):
    """
    账号输入
    """
    name = String()
    desc = String()

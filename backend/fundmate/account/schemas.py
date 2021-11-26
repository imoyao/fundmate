#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/27 18:08
"""
类比DRF中的serializer
"""
from apiflask import Schema
from apiflask.fields import Integer, String
from apiflask.validators import OneOf

from backend.fundmate.settings import RISK_TYPE


class CreateAccountSchema(Schema):
    """
    账本创建
    """
    '''
    各家解决方案：
    有知有行：名称、预期年化、投资时间、币种
    投资账本： 名称
    韭圈儿： 名称
    ---
    本系统：
    名称
    风险等级
    描述，即投资目标、投资年限等
    '''
    usable_risk_types = list(RISK_TYPE.keys())
    name = String(length=10)
    account_type = String(required=True, default='undefined', validate=OneOf(usable_risk_types))
    desc = String()


class AddAccountItemSchema(Schema):
    """
    创建账号后添加购买品种
    韭圈儿：购买平台，基金名称，持有金额，持有收益
    """
    pass


class AccountOutSchema(Schema):
    """
    账号信息返回
    """
    id = Integer()
    name = String()
    account_type = String()

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/27 18:08
"""
类比DRF中的serializer
"""
from apiflask import Schema
from apiflask.fields import Function, Integer, String
from apiflask.validators import Length, OneOf

from backend.fundmate import settings


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
    name = String(required=True, validate=Length(2, 10))
    account_type = String(required=True,
                          dump_default=settings.RiskTypeEnum.undefined.dk_name,
                          validate=OneOf(settings.RiskTypeEnum.input()))
    desc = String(validate=Length(max=300))
    rich_desc = String(validate=Length(max=1000))


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
    desc = String()


class CommitProducts(Schema):
    """
    用户提交自己购买的理财产品（如组合或者理财产品）
    """
    platform = String(required=True,
                      dump_default=settings.SupportInvestPltEnum.unknown.dk_value,
                      validate=OneOf(settings.SupportInvestPltEnum.input()))
    prod_type = String(required=True,
                       dump_default=None,
                       validate=OneOf(settings.SupportInvestCategoriesEnum.input()),
                       data_key='type')
    name = String(required=True)
    code = String(etadata={'title': '产品编码', 'description': '用户可以输入平台专属的编码，后期统一时更好处理'})


class InvestProductOut(Schema):
    """
    用户提交自己购买的理财产品（如组合或者理财产品）
    """
    plt_code = String()
    verified_code = String()
    platform = Function(lambda obj: obj.platform.dk_value,
                        metadata={
                            'title': '理财产品所属平台',
                            'description': f'{settings.PlatTypeEnum.comment()}'
                        })
    platform_name = Function(lambda obj: obj.platform.dk_display)
    prod_name = String(required=True)
    prod_code = String(etadata={'title': '产品编码', 'description': '在导入文件中输入的产品编码'})


class QueryInvestProduct(Schema):
    """
    用户提交自己购买的理财产品（如组合或者理财产品）
    """
    prod_name = String(required=True)
    platform = String(required=True,
                      dump_default=settings.SupportInvestPltEnum.unknown.dk_value,
                      validate=OneOf(settings.SupportInvestPltEnum.input()))
    plt_code = String()
    prod_type = String(required=False,
                       dump_default=None,
                       validate=OneOf(settings.SupportInvestCategoriesEnum.input()),
                       data_key='type')

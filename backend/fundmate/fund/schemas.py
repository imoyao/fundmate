#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/27 18:08
"""
类比DRF中的serializer
"""
from apiflask import PaginationSchema, Schema
from apiflask.fields import Date, Function, Integer, List, Method, Nested, Number, String
from apiflask.validators import Length, OneOf

from backend.fundmate import settings
from backend.fundmate.schema_ext import CustomPaginationSchema


class FundOutSchema(Schema):
    """
    详细信息
    """
    id = Integer()
    name = String()
    mgr = String()
    fund_code = String()
    created_at = Date()
    company = String()
    f_type = String()


class FundPortfolioMgrOutSchema(Schema):
    """
    组合管理员信息
    """
    code = String()
    name = String()
    plat_code = String()
    mgr_avatar_url = String()
    desc = String()


def get_risk_level(risk_type: str) -> str:
    return settings.RISK_TYPE.get(risk_type)


def get_platform(platform: str) -> str:
    return settings.PLAT_TYPE_DISPLAY.get(platform)


def display_risk(risk_type: str) -> str:
    return settings.RISK_TYPE_DISPLAY.get(risk_type)


class FundPortfolioOutSchema(Schema):
    """
    单个组合概览信息
    """
    portfolio_code = String(data_key='code')
    name = String(metadata={'title': '组合名称', 'description': '组合名称'})
    risk_level = Function(lambda obj: get_risk_level(obj.risk_type))
    risk_display = Function(lambda obj: display_risk(obj.risk_type))
    platform = String(metadata={'title': '组合所属平台', 'description': '具体请查看`platform_name`字段'})
    platform_name = Function(lambda obj: get_platform(obj.platform))


class FundPortfoliosPaginationSchema(CustomPaginationSchema):
    risk_type = String(default=None, validate=OneOf(settings.RISK_TYPE.keys()))


class FundPortfoliosOutSchema(Schema):
    """
    组合概览信息列表
    """
    portfolios = List(Nested(FundPortfolioOutSchema))
    pagination = Nested(PaginationSchema)


class FundPortfolioDetailOutSchema(Schema):
    """
    组合详细信息
    """

    def display_risk(self, obj):
        return settings.RISK_TYPE_DISPLAY.get(obj.get('risk_type'))

    # def get_platform(self, obj):
    #     return settings.PLAT_TYPE_DISPLAY.get(obj.get('platform'))

    id = Integer()
    name = String(metadata={'title': '组合名称', 'description': '组合名称'})
    ''':type
    返回值重命名，避免字段暴露 see also: https://apiflask.com/usage/#the-return-value-of-the-view-function
    [What if I want to use a different external field name]
    '''
    portfolio_code = String(data_key='code')
    code = String(data_key='plat_code')
    found_date = Date(data_key='create_date')
    risk_type = String(data_key='risk_str')
    risk_display = Function(lambda obj: display_risk(obj.get('risk_type')))
    platform = String(metadata={'title': '所属平台', 'description': '具体请查看`platform_name`字段'})
    platform_name = Function(lambda obj: get_platform(obj.get('platform')))
    risk_level = Function(lambda obj: get_risk_level(obj.get('risk_type')))
    invest_rate_of_return = Number(metadata={'title': '投资回报率', 'description': ''})
    annualized_rate_of_return = Number(metadata={'title': '年化回报率', 'description': ''})
    desc = String()
    rich_desc = String()
    last_adjust_date = Date()
    manager = Nested(FundPortfolioMgrOutSchema)


class FundSampleSchema(Schema):
    """
    简略信息，目前包含基金编码和基金名称
    """
    fund_code = String()
    name = String()


class FundPaginationOutSchema(Schema):
    """
    带分页器的基金信息输出
    TODO: 分页器用法（写文档时需要额外说明）
    """
    funds = List(Nested(FundSampleSchema))
    pagination = Nested(PaginationSchema)


class FundSearchKeySchema(Schema):
    q = String()


class FundMgrOutSchema(Schema):
    id = Integer()
    name = String()
    mgr_code = String()
    created_at = Date()
    company = String()


class FundCompanyOutSchema(Schema):
    id = Integer()
    code = String()
    name = String()
    full_name = String()
    tx_eval = Integer()
    create_date = Date()
    scale = Number()


class FundInSchema(Schema):
    code = String(validate=Length(5, 25))
    name = String(validate=Length(6, 40))


class SaleSchema(Schema):

    def as_name(self, obj):
        """
        如果有熟知的名字，则显示备注；否则，显示完整渠道名称
        :param obj:
        :return:
        """
        return obj.known_name or obj.name

    org_id = String(data_key='code')
    name = Method('as_name')


class MidSaleSchema(Schema):
    label = String()
    options = List(Nested(SaleSchema))


class FundSaleOutSchema(Schema):
    options = List(Nested(MidSaleSchema))
    # all = Nested(MidSaleSchema)

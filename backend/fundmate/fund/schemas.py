#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/27 18:08
"""
类比DRF中的serializer
"""
from apiflask import PaginationSchema, Schema
from apiflask.fields import Boolean, Date, Float, Function, Integer, List, Method, Nested, Number, String
from apiflask.validators import Equal, Length, OneOf

from backend.fundmate import settings
from backend.fundmate.fund.models import FundType
from backend.fundmate.schema_ext import CustomPaginationSchema
from backend.fundmate.user.models import User


def display_fund_type(fd_type_id: int) -> str:
    ft = FundType.query.filter_by(id=fd_type_id).one_or_none()
    if ft:
        return ft.name


class FundInSchema(Schema):
    code = String(validate=Length(5, 25))
    name = String(validate=Length(6, 40))


class FundOutSchema(Schema):
    """
    基金概览信息
    """
    id = Integer()
    fund_code = String()
    name = String()
    mgr = String()
    created_at = Date()
    company = String()
    f_type = String(data_key='fund_type')
    fund_type_display = Function(lambda obj: display_fund_type(obj.f_type))


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


class CompositionsSchema(Schema):
    fd_code = String(required=True,
                     Length=6,
                     data_key='code',
                     metadata={
                         'title': '组合品类编号',
                         'description': '未分配比例部分请按照现金（000000）分配'
                     })
    portion = Float(required=True,
                    min=0,
                    max=100,
                    min_inclusive=False,
                    data_key='ratio',
                    metadata={
                        'title': '投资比例',
                        'description': '请输入 (0-100] 之间的数字作为分配比例'
                    })


class FundPortfolioInSchema(Schema):
    name = String(required=True, validate=Length(2, 10))
    is_visible = Boolean(default=True)
    platform = String(load_default='own', validate=Equal('own'))  # 用户创建只能是own,不然会导致后续出错
    risk_type = String(default=None,
                       validate=OneOf(settings.RISK_TYPE.keys()),
                       metadata={
                           'title': '风险类型',
                           'description': f'{str(settings.RISK_TYPE_DISPLAY)}'
                       })
    desc = String(validate=Length(0, 300))
    rich_desc = String(validate=Length(0, 1000))
    compositions = List(Nested(CompositionsSchema))


class FundPortfolioPatchInSchema(Schema):
    name = String(required=True, validate=Length(2, 10))
    is_visible = Boolean(default=True)
    risk_type = String(default=None, validate=OneOf(settings.RISK_TYPE.keys()))
    desc = String(validate=Length(0, 300))
    rich_desc = String(validate=Length(0, 1000))
    adjust_comment = String(validate=Length(0, 300),
                            metadata={
                                'title': '调仓观点',
                                'description': '在进行调仓操作时，可以输入调仓理由和操作观点，以便后续进行投资复盘。'
                            })
    compositions = List(Nested(CompositionsSchema))


class FundPortfolioWithUserOutSchema(Schema):
    id = String(data_key='code')
    username = String(data_key='name')
    custom_avatar = String(data_key='mgr_avatar_url')
    desc = String(default='用户自述')


def internal_fpo_manager(obj):
    """
    内部用户自建组合的用户信息从`User`表中获取
    :param obj:
    :return:
    """
    if not obj.manager and obj.platform == 'own':
        mgr_id = int(obj.mgr_code)
        user = User.query.filter_by(id=mgr_id).one_or_none()
        # [python - Is it possible to use a schema for a marshmallow custom field? - Stack Overflow](
        # https://stackoverflow.com/questions/49802142/is-it-possible-to-use-a-schema-for-a-marshmallow-custom-field)
        # [Custom Fields — marshmallow 3.14.1 documentation](
        # https://marshmallow.readthedocs.io/en/stable/custom_fields.html)
        return FundPortfolioWithUserOutSchema().dump(user)


class FundPortfolioDetailOutSchema(Schema):
    """
    组合详细信息
    """
    id = Integer()
    name = String(metadata={'title': '组合名称', 'description': '组合名称'})
    '''
    返回值重命名，避免字段暴露 see also: https://apiflask.com/usage/#the-return-value-of-the-view-function
    [What if I want to use a different external field name]
    '''
    portfolio_code = String(data_key='code')
    code = String(data_key='plat_code')
    found_date = Date(data_key='create_date')
    risk_type = String()
    risk_display = Function(lambda obj: display_risk(obj.risk_type))
    platform = String(metadata={'title': '所属平台', 'description': '具体请查看`platform_name`字段'})
    platform_name = Function(lambda obj: get_platform(obj.platform))
    risk_level = Function(lambda obj: get_risk_level(obj.risk_type))
    invest_rate_of_return = Number(metadata={'title': '投资回报率', 'description': ''})
    annualized_rate_of_return = Number(metadata={'title': '年化回报率', 'description': ''})
    desc = String()
    rich_desc = String()
    last_adjust_date = Date()
    manager = Nested(FundPortfolioMgrOutSchema,
                     metadata={
                         'title': '组合管理者',
                         'description': '记录组合管理者的信息，包括姓名、所属平台、头像链接等信息'
                     })
    extra_owner = Function(lambda obj: internal_fpo_manager(obj),
                           metadata={
                               'title': '平台內建组合管理者信息',
                               'description': '系统除了依靠外部数据维护一部分组合外，内部用户也可以构建自由组合，此时用户信息从该字段中获取。'
                           })


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
    tx_eval = Integer(metadata={'title': '天相评级', 'description': '五星制，星级越高代表公司越好'})
    create_date = Date()
    scale = Number(metadata={'title': '资产规模', 'description': '管理资产规模(亿元)'})


class FundCompanyPaginationOutSchema(Schema):
    companies = List(Nested(FundCompanyOutSchema))
    pagination = Nested(PaginationSchema)


class FundMgrPaginationOutSchema(Schema):
    managers = List(Nested(FundMgrOutSchema))
    pagination = Nested(PaginationSchema)


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

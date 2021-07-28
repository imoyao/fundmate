#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/27 18:08
"""
类比DRF中的serializer
"""
from apiflask import APIBlueprint, Schema, abort, input, output
from apiflask.fields import Date, Function, Integer, Number, String
from apiflask.validators import Length


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
    fund_type = String()


class FundSampleSchema(Schema):
    """
    简略信息，目前包含基金编码和基金名称
    """
    fund_code = String()
    name = String()


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

    class Meta:
        fields = ('id', 'name')


class FundSaleOutSchema(Schema):
    # [python - Is it possible to use a schema for a marshmallow custom field? - Stack Overflow](https://stackoverflow.com/questions/49802142/is-it-possible-to-use-a-schema-for-a-marshmallow-custom-field)
    id = String()
    name = Function(lambda obj: SaleSchema(many=True).dump(obj.as_name()))

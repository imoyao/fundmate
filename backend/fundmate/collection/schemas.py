# -*- coding: utf-8 -*-
"""
@Time ： 2022/12/19 20:57
@File ：schemas.py
@IDE ：PyCharm
"""
from apiflask import Schema
from apiflask.fields import Function, Integer, String
from apiflask.validators import OneOf, Range

from marshmallow import ValidationError
from marshmallow.fields import List, Nested
from marshmallow.validate import Length

from backend.fundmate import settings
from backend.fundmate.collection.logics import lookup_collection
from backend.fundmate.collection.models import LabelsOfCollection
from backend.fundmate.fund.schemas import FundSampleSchema
from backend.fundmate.schema_ext import CustomPaginationSchema


class QueryCollectionsSchema(Schema):
    collection_type = String(required=True,
                             dump_default=settings.SupportCollectionsEnum.fund.dk_value,
                             validate=OneOf(settings.SupportCollectionsEnum.input()))
    page = Integer(load_default=1)  # 设置默认页面为 1
    # 将默认值设置为 20，并确保该值不超过 30
    per_page = Integer(load_default=20, validate=Range(max=30))


def get_collection_details(collect_type, identify):
    _inst = lookup_collection(collect_type, identify)
    if _inst:
        if collect_type == settings.SupportCollectionsEnum.fund.dk_value:
            # TODO: 需要使用复杂接口处理成带各种指标的数据
            fund_schema = FundSampleSchema()
            _result = fund_schema.dump(_inst)
            return _result
        else:
            pass


class CollectionItemOutSchema(Schema):
    id = Function(lambda obj: obj.id, required=True)
    info = Function(lambda obj: get_collection_details(obj.collection_type.dk_value, obj.identify))


class CollectionsOutSchema(Schema):
    collections = List(Nested(CollectionItemOutSchema))
    pagination = Nested(CustomPaginationSchema)


class LabelItemOutSchema(Schema):
    id = Integer()
    name = String()
    color = String()
    desc = String()


class LabelsOutSchema(Schema):
    labels = List(Nested(LabelItemOutSchema))
    pagination = Nested(CustomPaginationSchema)


class WithIdSchema(Schema):
    id = Integer(required=True)


class CreateCollectionSchema(Schema):
    collection_type = String(required=True,
                             dump_default=settings.SupportCollectionsEnum.fund.dk_value,
                             validate=OneOf(settings.SupportCollectionsEnum.input()))
    identify = String(required=True)


def check_color(hex_str: str):
    label = LabelsOfCollection()
    if not label.validate_color(hex_str):
        raise ValidationError('请输入正确的 HEX 值字符')


class CreateLabelSchema(Schema):
    name = String(required=True, validate=Length(max=10))
    color = String(required=True, validate=check_color)
    desc = String()


class UpdateLabelSchema(Schema):
    name = String(validate=Length(max=10))
    color = String(validate=check_color)
    desc = String()


class UpdateLabelOutSchema(Schema):
    labels = List(Nested(LabelItemOutSchema))


class UpdateLabelOfCollectionsSchema(Schema):
    labels = List(Integer())

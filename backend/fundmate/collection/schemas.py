# -*- coding: utf-8 -*-
"""
@Time ： 2022/12/19 20:57
@File ：schemas.py
@IDE ：PyCharm
"""
from apiflask import Schema
from apiflask.fields import Function, Integer, String
from apiflask.validators import OneOf, Range

from marshmallow.fields import List, Nested

from backend.fundmate import settings
from backend.fundmate.schema_ext import CustomPaginationSchema


class QueryCollectionsSchema(Schema):
    collection_type = String(required=True,
                             dump_default=settings.SupportCollectionsEnum.fund.dk_value,
                             validate=OneOf(settings.SupportCollectionsEnum.input()))
    page = Integer(load_default=1)  # 设置默认页面为 1
    # 将默认值设置为 20，并确保该值不超过 30
    per_page = Integer(load_default=20, validate=Range(max=30))


def get_collection_details(identify, collect_type):
    pass


class CollectionOutSchema(Schema):
    id = Integer()
    info = Function(lambda obj: get_collection_details(obj.identify, obj.collect_type))


class CollectionsOutSchema(Schema):
    collections = List(Nested(CollectionOutSchema))
    pagination = Nested(CustomPaginationSchema)


class NewCollectionOutSchema(Schema):
    id = Integer(required=True)


class CreateCollectionSchema(Schema):
    collection_type = String(required=True,
                             dump_default=settings.SupportCollectionsEnum.fund.dk_value,
                             validate=OneOf(settings.SupportCollectionsEnum.input()))
    identify = String(required=True)


class DeleteCollectionSchema(Schema):
    """
    删除自选
    """
    collection_type = String(required=True,
                             dump_default=settings.SupportCollectionsEnum.fund.dk_value,
                             validate=OneOf(settings.SupportCollectionsEnum.input()))
    identify = String(required=True)

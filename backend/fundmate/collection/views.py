# -*- coding: utf-8 -*-
"""
@Time ： 2022/12/19 20:52
@File ：views.py
@IDE ：PyCharm
"""
from typing import Dict

from apiflask import APIBlueprint, abort, pagination_builder
from flask.views import MethodView
from flask_praetorian import auth_required, current_user

from backend.fundmate.collection.models import Collections
from backend.fundmate.collection.schemas import (
    CollectionsOutSchema,
    CreateCollectionSchema,
    DeleteCollectionSchema,
    NewCollectionOutSchema,
    QueryCollectionsSchema,
)


bp = APIBlueprint('collections', __name__, url_prefix='/collections')


@bp.route('/')
class CollectionsView(MethodView):
    """
    用户自选
    """
    @auth_required
    @bp.input(QueryCollectionsSchema, 'query')
    @bp.output(CollectionsOutSchema)
    @bp.doc(security='Bearer')
    def get(self, query: Dict):
        """
        获取自选信息

        根据平台和产品名称查询产品的分类和编码；如果没有查询到，则可以使用post请求创建
        :param query:
        :return:
        """
        user = current_user()
        creator_id = user.id
        collection_type = query.get('collection_type')
        pagination = Collections.query.filter_by(collection_type=collection_type, creator_id=creator_id).paginate(
            page=query.get('page'),
            per_page=query.get('per_page')
        )
        collections = pagination.items
        if collections:
            return {
                'collections': collections,
                'pagination': pagination_builder(pagination)
            }
        else:
            abort(404)

    @auth_required
    @bp.input(CreateCollectionSchema)
    @bp.output(NewCollectionOutSchema)
    @bp.doc(security='Bearer')
    def post(self, data: Dict):
        """
        用户添加自选
        :return:
        """
        user = current_user()
        creator_id = user.id
        data['creator_id'] = creator_id
        prod_inst = Collections.create(**data)
        return prod_inst

    @auth_required
    @bp.input(DeleteCollectionSchema)
    @bp.output({}, 204)
    @bp.doc(security='Bearer')
    def delete(self, data: Dict):
        """用户删除自选"""
        pass

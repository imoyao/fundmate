# -*- coding: utf-8 -*-
"""
@Time ： 2022/12/19 20:52
@File ：views.py
@IDE ：PyCharm
"""
from typing import Dict

from apiflask import APIBlueprint, abort, pagination_builder
from apiflask.views import MethodView
from flask_praetorian import auth_required, current_user

from backend.fundmate.collection.logics import create_default_category, create_default_labels, lookup_collection
from backend.fundmate.collection.models import CategoriesOfCollection, Collection, LabelsOfCollection
from backend.fundmate.collection.schemas import (
    CategoriesOutSchema,
    CategoryItemOutSchema,
    CollectionsOutSchema,
    CreateCategorySchema,
    CreateCollectionSchema,
    CreateLabelSchema,
    CustomQueryCategoryPaginationSchema,
    LabelItemOutSchema,
    LabelsOutSchema,
    QueryCollectionsSchema,
    UpdateCategorySchema,
    UpdateLabelOfCollectionsSchema,
    UpdateLabelOutSchema,
    UpdateLabelSchema,
    WithIdSchema,
)
from backend.fundmate.errors import ClientError, HTTPClientError, UserInputError
from backend.fundmate.extensions import db
from backend.fundmate.schema_ext import CustomPaginationSchema
from backend.fundmate.settings import DEFAULT_CATEGORY_NAME


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
        获取指定自选的详情信息，包括：
        1. 自选的标签
        2. 自选的分类
        3. 自选的备注（TODO）
        4. 如果购买过，则返回交易信息

        根据平台和产品名称查询产品的分类和编码；如果没有查询到，则可以使用post请求创建
        :param query:
        :return:
        """
        user = current_user()
        creator_id = user.id
        collection_type = query.get('collection_type')
        pagination = Collection.query.filter_by(collection_type=collection_type, creator_id=creator_id).paginate(
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
    @bp.output(WithIdSchema)
    @bp.doc(security='Bearer')
    def post(self, data: Dict):
        """
        用户添加自选
        :return:
        """
        user = current_user()
        creator_id = user.id

        collection_type = data.get('collection_type')
        identify = data.get('identify')
        is_collected = Collection.check_has_collected(creator_id, collection_type, identify)
        if not is_collected:
            col_inst = lookup_collection(collection_type, identify)

            if col_inst:
                data['creator_id'] = creator_id
                prod_inst = Collection.create(**data)
                # 系统创建默认 labels 和 分组
                create_default_labels(creator_id)
                create_default_category(creator_id, collection_type)
                return prod_inst
            error = ClientError.COLLECTION_ERR
            extra_data = {'error_code': error.code, 'docs': ''}
            raise HTTPClientError(message=error.msg, extra_data=extra_data)
        error = ClientError.HAS_CREATED_ERR
        error_msg = '自选产品已存在，请勿重复创建'
        extra_data = {'error_code': error.code, 'docs': ''}
        raise HTTPClientError(message=error_msg, extra_data=extra_data)

    @auth_required
    @bp.input(WithIdSchema)
    @bp.output({}, 204)
    @bp.doc(security='Bearer')
    def delete(self, data: Dict):
        """用户删除自选"""
        collection_id = data.get('id')
        _collect_inst = Collection.get_by_id(collection_id)
        if _collect_inst:
            user = current_user()
            creator_id = user.id
            if _collect_inst.creator_id == creator_id:
                _collect_inst.delete()
            else:
                error = UserInputError.FORBIDDEN_DELETE_ERR
                msg = '删除失败，请确认自选产品存在。'
                extra_data = {'error_code': error.code, 'docs': ''}
                raise HTTPClientError(403, message=msg, extra_data=extra_data)
        else:
            abort(404)


@bp.route('/labels')
class LabelsOfCollectionsView(MethodView):
    """
    自选标签管理
    """

    @auth_required
    @bp.input(CustomPaginationSchema, 'query')
    @bp.output(LabelsOutSchema)
    @bp.doc(security='Bearer')
    def get(self, query: Dict):
        """
        获取用户创建的标签
        :param query:
        :return:
        """
        user = current_user()
        creator_id = user.id
        pagination = LabelsOfCollection.query.filter_by(creator_id=creator_id).paginate(
            page=query.get('page'),
            per_page=query.get('per_page')
        )
        labels = pagination.items
        if labels:
            return {
                'labels': labels,
                'pagination': pagination_builder(pagination)
            }
        else:
            abort(404)

    @auth_required
    @bp.input(CreateLabelSchema)
    @bp.output(WithIdSchema)
    @bp.doc(security='Bearer')
    def post(self, data: Dict):
        """
        创建标签

        用户第一次添加自选时，默认创建默认的labels

        :param data:
        :return:
        """
        user = current_user()
        creator_id = user.id

        label_name = data.get('name')
        has_created = LabelsOfCollection.has_same_label_name_by_user(creator_id, label_name)
        if not has_created:
            data['creator_id'] = creator_id
            label_inst = LabelsOfCollection.create(**data)
            return label_inst
        error = ClientError.HAS_CREATED_ERR
        error_msg = '标签名已存在，请勿重复创建'
        extra_data = {'error_code': error.code, 'docs': ''}
        raise HTTPClientError(message=error_msg, extra_data=extra_data)


@bp.route('/categories')
class CategoriesOfCollectionsView(MethodView):
    """
    自选产品分类管理
    """

    @auth_required
    @bp.input(CustomQueryCategoryPaginationSchema, 'query')
    @bp.output(CategoriesOutSchema)
    @bp.doc(security='Bearer')
    def get(self, query: Dict):
        """
        获取某个自选分类下用户创建的分组
        :param query:
        :return:
        """
        user = current_user()
        creator_id = user.id
        pagination = CategoriesOfCollection.query.filter_by(creator_id=creator_id).paginate(
            page=query.get('page'),
            per_page=query.get('per_page')
        )
        categories = pagination.items
        if categories:
            return {
                'categories': categories,
                'pagination': pagination_builder(pagination)
            }
        else:
            abort(404)

    @auth_required
    @bp.input(CreateCategorySchema)
    @bp.output(WithIdSchema)
    @bp.doc(security='Bearer')
    def post(self, data: Dict):
        """
        创建标签
        :param data:
        :return:
        """
        user = current_user()
        creator_id = user.id

        category_name = data.get('name')
        collection_type = data.get('collection_type')
        # 同类别同用户不能包含同名
        has_created = CategoriesOfCollection.has_same_category_name_by_col(creator_id, collection_type, category_name)
        if not has_created:
            data['creator_id'] = creator_id
            label_inst = CategoriesOfCollection.create(**data)
            return label_inst
        error = ClientError.HAS_CREATED_ERR
        error_msg = '分组名已存在，请勿重复创建'
        extra_data = {'error_code': error.code, 'docs': ''}
        raise HTTPClientError(message=error_msg, extra_data=extra_data)


@bp.route('/<collection_id>/labels')
class ManageLabelsOfCollectionsView(MethodView):
    """
    自选单品的标签管理
    """

    @auth_required
    @bp.input(UpdateLabelOfCollectionsSchema)
    @bp.output(UpdateLabelOutSchema, status_code=205)
    @bp.doc(security='Bearer')
    def patch(self, collection_id: int, data: Dict):
        """
        给某个品类增加或者删除 label，用户传输目前的完整 label id list
        """
        _col_inst = Collection.get_by_id(collection_id)
        if _col_inst:
            user = current_user()
            user_id = user.id
            creator_id = _col_inst.creator_id
            if creator_id == user_id:
                labels = data.get('labels')
                labels_of_user = LabelsOfCollection.labels_of_user(user_id)
                labels_id_list_of_user = [label.id for label in labels_of_user]

                ipt_labels = set(labels)
                user_labels = set(labels_id_list_of_user)

                if ipt_labels.issubset(user_labels):
                    if ipt_labels:
                        new_labels = db.session.query(LabelsOfCollection).filter(
                            LabelsOfCollection.id.in_(list(ipt_labels))).all()
                        _col_inst.labels = new_labels
                    else:
                        new_labels = []
                        _col_inst.labels = new_labels
                    db.session.commit()

                    return {
                        'labels': new_labels
                    }
                else:
                    error = UserInputError.LABEL_IS_NOT_EXIST_ERR
                    msg = '修改失败，请确认输入是否正确。'
                    extra_data = {'error_code': error.code, 'docs': ''}
                    raise HTTPClientError(400, message=msg, extra_data=extra_data)

            else:
                error = UserInputError.FORBIDDEN_UPDATE_ERR
                msg = '修改失败，请确认输入是否正确。'
                extra_data = {'error_code': error.code, 'docs': ''}
                raise HTTPClientError(403, message=msg, extra_data=extra_data)
        else:
            abort(404)


@bp.route('/labels/<label_id>')
class DetailOfLabelsOfCollectionsView(MethodView):
    """
    单个标签的管理
    """

    @auth_required
    @bp.input(UpdateLabelSchema)
    @bp.output(LabelItemOutSchema)
    @bp.doc(security='Bearer')
    def patch(self, label_id: int, data: Dict):
        """
        修改某个 label 的属性
        :param label_id:
        :param data:
        :return:
        """
        _label_inst = LabelsOfCollection.get_by_id(label_id)
        if _label_inst:
            user = current_user()
            creator_id = user.id
            if _label_inst.creator_id == creator_id:
                _label_info = _label_inst.update(**data)
                return _label_info
            else:
                error = UserInputError.FORBIDDEN_UPDATE_ERR
                msg = '更新失败，请确认标签存在。'
                extra_data = {'error_code': error.code, 'docs': ''}
                raise HTTPClientError(403, message=msg, extra_data=extra_data)
        else:
            abort(404)

    @auth_required
    @bp.output({}, 204)
    @bp.doc(security='Bearer')
    def delete(self, label_id: int):
        """
        删除某个指定label

        # INFO: 删除前提示用户会将标签从所有自选品类中移除，用户确认之后直接移除
        :return:
        """
        _inst = LabelsOfCollection.get_by_id(label_id)
        if _inst:
            user = current_user()
            creator_id = user.id
            if _inst.creator_id == creator_id:
                _inst.delete()
            else:
                error = UserInputError.FORBIDDEN_DELETE_ERR
                msg = '删除失败，请确认标签存在。'
                extra_data = {'error_code': error.code, 'docs': ''}
                raise HTTPClientError(403, message=msg, extra_data=extra_data)
        else:
            abort(404)


@bp.route('/categories/<category_id>')
class DetailOfCategoryOfCollectionsView(MethodView):
    """
    单个分组的管理
    """

    @auth_required
    @bp.input(UpdateCategorySchema)
    @bp.output(CategoryItemOutSchema)
    @bp.doc(security='Bearer')
    def patch(self, category_id: int, data: Dict):
        """
        修改某个 category 的属性
        :param category_id:
        :param data:
        :return:
        """
        _inst = CategoriesOfCollection.get_by_id(category_id)
        if _inst:
            user = current_user()
            creator_id = user.id
            if _inst.creator_id == creator_id:
                if _inst.name == DEFAULT_CATEGORY_NAME:
                    error = UserInputError.FORBIDDEN_UPDATE_ERR
                    msg = '更新失败，系统默认分组不允许更新。'
                    extra_data = {'error_code': error.code, 'docs': ''}
                    raise HTTPClientError(403, message=msg, extra_data=extra_data)
                _inst_info = _inst.update(**data)
                return _inst_info
            else:
                error = UserInputError.FORBIDDEN_UPDATE_ERR
                msg = '更新失败，请确认分组存在。'
                extra_data = {'error_code': error.code, 'docs': ''}
                raise HTTPClientError(403, message=msg, extra_data=extra_data)
        else:
            abort(404)

    @auth_required
    @bp.output({}, 204)
    @bp.doc(security='Bearer')
    def delete(self, category_id: int):
        """
        删除某个指定分组

        # INFO: 删除前提示用户会将标签从所有自选品类中移除，用户确认之后直接移除
        :return:
        """
        _inst = CategoriesOfCollection.get_by_id(category_id)
        if _inst:
            user = current_user()
            creator_id = user.id
            if _inst.creator_id == creator_id:
                # 系统默认创建的分组不能删除
                if _inst.name == DEFAULT_CATEGORY_NAME:
                    error = UserInputError.FORBIDDEN_DELETE_ERR
                    msg = '删除失败，系统默认分组不允许删除。'
                    extra_data = {'error_code': error.code, 'docs': ''}
                    raise HTTPClientError(403, message=msg, extra_data=extra_data)

                _inst.delete()
            else:
                error = UserInputError.FORBIDDEN_DELETE_ERR
                msg = '删除失败，请确认标签存在。'
                extra_data = {'error_code': error.code, 'docs': ''}
                raise HTTPClientError(403, message=msg, extra_data=extra_data)
        else:
            abort(404)

# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2023/1/5 22:10
# File : test_collection_views.py
# FIXME: 目前由于基础数据不足，没有测试指数、可转债等相关自选接口
import copy
import json
import random

from factory import Faker

import pytest
from faker import Faker as RealFaker

from backend.fundmate import settings
from backend.fundmate.collection.models import LabelsOfCollection
from backend.fundmate.errors import ClientError, UserInputError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.user.models import User
from backend.tests.collection.collection_teardown import (
    delete_all_categories,
    delete_all_collections,
    delete_all_labels,
)

from ..factories import CategoryOfCollectionFactory, FundFactory, LabelOfCollectionFactory, UserFactory


base_collections_endpoint = 'collections/'


@pytest.fixture(scope='module')
def create_base_data():
    """
    # 如何造假数据？ https://testerhome.com/topics/17088
    添加自选时必须保证有一定的基础数据，然后才能去添加自选
    :return:
    """
    funds = list()
    base_data = dict()
    for _ in range(5):
        # 创建基金
        fund = FundFactory()
        funds.append(fund.fund_code)
        # TODO:创建股票、……
    base_data['fund'] = funds
    return base_data


def create_collection(client, headers=None, data=None):
    if not data:
        data = dict()
    _result = client.post(base_collections_endpoint, headers=headers, json=data)
    return _result


class TestCollections:
    @staticmethod
    def get_collection(client, headers=None, params=None):
        if not params:
            params = dict()
        #  get url 携带参数：https://stackoverflow.com/a/28056409
        _result = client.get(base_collections_endpoint, headers=headers, query_string=params)
        return _result

    @staticmethod
    def delete_collection(client, headers=None, data=None):
        if not data:
            data = dict()
        _result = client.delete(base_collections_endpoint, headers=headers, json=data)
        return _result

    @pytest.fixture(scope="function", autouse=True)
    def delete_collection_from_db(self, request):
        """
        删除collection
        :return:
        """

        request.addfinalizer(delete_all_collections)
        return 0

    def test_get_collections(self, db, client, bearer_header, create_base_data):
        # auth required
        no_auth_result = self.get_collection(client)
        assert no_auth_result.status_code == 401
        # 数据为空
        no_data_result = self.get_collection(client, headers=bearer_header)
        no_data_resp = no_data_result.json
        assert 'Missing data for required field' in json.dumps(no_data_resp)

        # 数据库数据为空
        params = {'collection_type': settings.SupportCollectionsEnum.fund.dk_value}
        with_collection_type_result = self.get_collection(client, headers=bearer_header, params=params)
        assert with_collection_type_result.status_code == 404

        # 先创建数据然后再获取
        fund_list = create_base_data.get('fund')
        for fund_code in fund_list:
            collect_data = {'collection_type': settings.SupportCollectionsEnum.fund.dk_value, 'identify': fund_code}
            result = create_collection(client, bearer_header, collect_data)
            assert result.status_code == 200

        with_data_result = self.get_collection(client, headers=bearer_header, params=params)
        logger.info(with_data_result.json)
        with_data_resp = with_data_result.json
        assert with_data_result.status_code == 200
        assert 'collections' in with_data_resp
        collections = with_data_resp.get('collections')
        assert collections
        random_item = random.choice(collections)
        assert isinstance(random_item.get('id'), int)
        item_info = random_item.get('info')
        assert 'fund_code' in item_info and 'name' in item_info
        _labels_of_col = item_info.get('labels')
        if _labels_of_col:
            assert _labels_of_col
            label_item_of_col = random.choice(_labels_of_col)
            assert 'color' in label_item_of_col and 'name' in label_item_of_col and 'id' in label_item_of_col
        # 获取股票
        stock_params = {'collection_type': settings.SupportCollectionsEnum.stock.dk_value}
        stack_with_data_result = self.get_collection(client, headers=bearer_header, params=stock_params)
        assert stack_with_data_result.status_code != 200

    def test_create_collections(self, client, bearer_header, create_base_data):
        # 基金数据组装
        fund_list = create_base_data.get('fund')
        logger.info(f'{fund_list}')
        fund_code = random.choice(fund_list)
        assert fund_code.isdigit()
        collect_data = {'collection_type': settings.SupportCollectionsEnum.fund.dk_value, 'identify': fund_code}

        # 测试不带认证参数
        no_auth_result = create_collection(client)
        no_auth_resp = no_auth_result.json
        logger.info(no_auth_resp)
        assert no_auth_result.status_code == 401

        # 创建自选基金
        result = create_collection(client, bearer_header, collect_data)
        resp = result.json
        assert result.status_code == 200
        assert resp
        _inst_id = resp.get('id')
        assert _inst_id

        # 测试重复自选基金
        re_create_fund_result = create_collection(client, bearer_header, collect_data)
        re_fund_resp = re_create_fund_result.json
        logger.info(re_fund_resp)
        assert re_create_fund_result.status_code != 200
        assert re_fund_resp.get('error_code') == ClientError.HAS_CREATED_ERR.code

        # 测试不带参数
        no_data_create_fund_result = create_collection(client, headers=bearer_header)
        no_data_fund_resp = no_data_create_fund_result.json
        assert re_create_fund_result.status_code == 400
        assert 'Missing data for required field' in json.dumps(no_data_fund_resp)

        # 测试自选产品不存在的状况
        def func_code_404(exists_fund_list):
            fund_code_404 = Faker("random_number", digits=6, fix_len=True)
            code_404_str = str(fund_code_404)
            if code_404_str not in exists_fund_list:
                return code_404_str
            else:
                func_code_404(exists_fund_list)

        _code_404 = func_code_404(fund_list)
        collect_data_404 = {'collection_type': settings.SupportCollectionsEnum.fund.dk_value, 'identify': _code_404}
        data_404_create_fund_result = create_collection(client, bearer_header, collect_data_404)
        data_404_fund_resp = data_404_create_fund_result.json
        assert data_404_create_fund_result.status_code == 400
        assert data_404_fund_resp.get('error_code') == ClientError.COLLECTION_ERR.code
        assert data_404_fund_resp.get('message') == ClientError.COLLECTION_ERR.msg

    def test_delete_collections(self, client, auth, bearer_header, create_base_data):
        # 基金数据组装
        fund_list = create_base_data.get('fund')
        fund_code = random.choice(fund_list)
        assert fund_code.isdigit()
        collect_data = {'collection_type': settings.SupportCollectionsEnum.fund.dk_value, 'identify': fund_code}
        result = create_collection(client, bearer_header, collect_data)
        resp = result.json
        assert result.status_code == 200
        assert resp

        # 删除不是自己的自选
        faker = RealFaker()
        password = faker.password()
        user = UserFactory(password=password)
        _inst_id = resp.get('id')
        assert _inst_id
        delete_data = {'id': _inst_id}
        token = auth.token(username=user.username, password=password)
        _headers = {'Content-Type': 'application/json',
                    'Authorization': "Bearer " + token}
        not_mine_del_result = self.delete_collection(client, _headers, delete_data)
        assert not_mine_del_result.status_code == 403
        deny_delete_resp = not_mine_del_result.json
        error_msg = deny_delete_resp.get('message')
        error_code = deny_delete_resp.get('error_code')
        assert error_msg
        forbidden_delete_others_collection_error = UserInputError.FORBIDDEN_DELETE_OTHERS_ERR
        assert '删除失败' in error_msg
        assert error_code == forbidden_delete_others_collection_error.code

        # 删除刚才创建的
        assert _inst_id
        delete_data = {'id': _inst_id}
        del_result = self.delete_collection(client, bearer_header, delete_data)
        assert del_result.status_code == 204

        # 删除不存在的
        delete_no_data = {'id': _inst_id + 1}
        delete_no_data_result = self.delete_collection(client, bearer_header, delete_no_data)
        assert delete_no_data_result.status_code == 404


base_label_endpoint = 'labels'
label_endpoint = base_collections_endpoint + base_label_endpoint


def create_label(client, headers=None, data=None):
    if not data:
        data = dict()
    _result = client.post(label_endpoint, headers=headers, json=data)
    return _result


class TestLabels:

    @staticmethod
    def get_labels(client, headers=None, params=None):
        if not params:
            params = dict()
        #  get url 携带参数：https://stackoverflow.com/a/28056409
        _result = client.get(label_endpoint, headers=headers, query_string=params)
        return _result

    @staticmethod
    @pytest.fixture(scope="function", autouse=True)
    def delete_label_from_db(request):
        """
        删除labels
        :return:
        """
        request.addfinalizer(delete_all_labels)
        return 0

    def test_get_labels(self, db, client, bearer_header, create_base_data):
        # auth required
        no_auth_result = self.get_labels(client)
        assert no_auth_result.status_code == 401
        # 数据为空
        no_data_result = self.get_labels(client, headers=bearer_header)
        assert no_data_result.status_code == 404

        # 先创建数据然后再获取
        LabelOfCollectionFactory()
        with_data_result = self.get_labels(client, headers=bearer_header)
        logger.info(with_data_result.json)
        with_data_resp = with_data_result.json
        assert with_data_result.status_code == 200
        assert 'labels' in with_data_resp
        labels = with_data_resp.get('labels')
        assert labels
        random_item = random.choice(labels)
        assert isinstance(random_item.get('id'), int)
        assert random_item.get('name')
        assert random_item.get('color').startswith('#')

    @pytest.mark.parametrize("label_data",
                             [({'name': 'YYDS', 'color': '#2ba245', 'desc': '那些神一样的基金！'}),
                              ({'name': '猪队友', 'color': '#c8595b'})])
    def test_create_label(self, client, auth, bearer_header, label_data):
        # 测试不带认证参数
        no_auth_result = create_label(client)
        no_auth_resp = no_auth_result.json
        logger.info(no_auth_resp)
        assert no_auth_result.status_code == 401

        # 创建label
        result = create_label(client, bearer_header, label_data)
        resp = result.json
        assert result.status_code == 200
        assert resp
        _inst_id = resp.get('id')
        assert _inst_id

        # 测试重复创建label
        re_create_fund_result = create_label(client, bearer_header, label_data)
        re_fund_resp = re_create_fund_result.json
        logger.info(re_fund_resp)
        assert re_create_fund_result.status_code != 200
        assert re_fund_resp.get('error_code') == ClientError.HAS_CREATED_ERR.code
        # 测试另一个人创建同名label
        faker = RealFaker()
        password = faker.password()
        user = UserFactory(password=password)
        token = auth.token(username=user.username, password=password)
        _headers = {'Content-Type': 'application/json',
                    'Authorization': "Bearer " + token}
        other_re_create_label_result = create_label(client, _headers, label_data)
        other_re_label_resp = other_re_create_label_result.json
        logger.info(other_re_label_resp)
        assert other_re_create_label_result.status_code == 200

        # 测试不带参数
        no_data_create_fund_result = create_label(client, headers=bearer_header)
        no_data_fund_resp = no_data_create_fund_result.json
        assert no_data_create_fund_result.status_code == 422
        assert 'Missing data for required field' in json.dumps(no_data_fund_resp)


base_category_endpoint = 'categories'
category_endpoint = base_collections_endpoint + base_category_endpoint


def create_category(client, headers=None, data=None):
    """
    封装创建分组的操作
    :param client:
    :param headers:
    :param data:
    :return:
    """
    if not data:
        data = dict()
    _result = client.post(category_endpoint, headers=headers, json=data)
    return _result


class TestCategories:

    @staticmethod
    def get_categories(client, headers=None, params=None):
        if not params:
            params = dict()
        #  get url 携带参数：https://stackoverflow.com/a/28056409
        _result = client.get(category_endpoint, headers=headers, query_string=params)
        return _result

    @staticmethod
    @pytest.fixture(scope="function", autouse=True)
    def delete_category_from_db(request):
        """
        删除labels
        :return:
        """
        request.addfinalizer(delete_all_categories)
        return 0

    def test_get_categories(self, db, client, bearer_header, create_base_data):
        # auth required
        no_auth_result = self.get_categories(client)
        assert no_auth_result.status_code == 401
        # 数据为空
        no_data_result = self.get_categories(client, headers=bearer_header)
        assert no_data_result.status_code == 422

        # 携带必选参数
        _query_data = {'collection_type': settings.SupportCollectionsEnum.fund.dk_value}

        no_data_result = self.get_categories(client, headers=bearer_header, params=_query_data)
        assert no_data_result.status_code == 404

        # 先创建数据然后再获取
        CategoryOfCollectionFactory(name='待到山花烂漫时')
        with_data_result = self.get_categories(client, headers=bearer_header, params=_query_data)
        logger.info(with_data_result.json)
        with_data_resp = with_data_result.json
        assert with_data_result.status_code == 200
        assert 'categories' in with_data_resp
        categories = with_data_resp.get('categories')
        assert categories
        random_item = random.choice(categories)
        assert isinstance(random_item.get('id'), int)
        assert isinstance(random_item.get('count'), int)
        assert random_item.get('name')

    @pytest.mark.parametrize("category_data",
                             [({'name': '嘲风优选'}),
                              ({'name': '超越巴菲特'})])
    def test_create_category(self, client, auth, bearer_header, category_data):
        # 测试不带认证参数
        no_auth_result = create_category(client)
        no_auth_resp = no_auth_result.json
        logger.info(no_auth_resp)
        assert no_auth_result.status_code == 401
        # 测试不带类别数据
        result = create_category(client, bearer_header, category_data)
        assert result.status_code == 422

        _base_data = {'collection_type': settings.SupportCollectionsEnum.fund.dk_value}
        # 创建category
        category_data.update(_base_data)
        result = create_category(client, bearer_header, category_data)
        resp = result.json
        assert result.status_code == 200
        assert resp
        _inst_id = resp.get('id')
        assert _inst_id

        # 测试重复创建category
        re_create_fund_result = create_category(client, bearer_header, category_data)
        re_fund_resp = re_create_fund_result.json
        logger.info(re_fund_resp)
        assert re_create_fund_result.status_code != 200
        assert re_fund_resp.get('error_code') == ClientError.HAS_CREATED_ERR.code

        # 测试为不同类别创建同名category
        other_category_data = copy.deepcopy(category_data)
        other_category_data['collection_type'] = settings.SupportCollectionsEnum.bond.dk_value
        other_re_create_fund_result = create_category(client, bearer_header, other_category_data)
        assert other_re_create_fund_result.status_code == 200

        # 测试另一个人创建同名label
        faker = RealFaker()
        password = faker.password()
        user = UserFactory(password=password)
        token = auth.token(username=user.username, password=password)
        _headers = {'Content-Type': 'application/json',
                    'Authorization': "Bearer " + token}
        other_re_create_result = create_category(client, _headers, category_data)
        assert other_re_create_result.status_code == 200

        # 测试不带参数
        no_data_create_fund_result = create_category(client, headers=bearer_header)
        no_data_fund_resp = no_data_create_fund_result.json
        assert no_data_create_fund_result.status_code == 422
        assert 'Missing data for required field' in json.dumps(no_data_fund_resp)


def endpoint_of_label(label_id):
    """
    拼接路由
    :param label_id:
    :return:
    """
    if label_id:
        return label_endpoint + f'/{label_id}'
    else:
        return label_endpoint


def collection_labels_endpoint(collection_id):
    if collection_id:
        return base_collections_endpoint + str(collection_id) + '/' + base_label_endpoint


class TestManageLabelsOfCollectionsView:
    def teardown(self):
        delete_all_labels()
        delete_all_collections()

    @staticmethod
    def patch_labels(client, headers=None, collection_id=None, data=None):
        if not data:
            data = dict()
        _endpoint = collection_labels_endpoint(collection_id)
        _result = client.patch(_endpoint, headers=headers, json=data)
        return _result

    def test_patch_labels_of_collections(self, client, auth, bearer_header, create_base_data):
        labels_data = {'labels': []}
        no_data_result = self.patch_labels(client, headers=bearer_header, collection_id=10086, data=labels_data)
        assert no_data_result.status_code == 404
        # 基金数据组装
        fund_list = create_base_data.get('fund')
        logger.info(f'{fund_list}')
        fund_code = random.choice(fund_list)
        assert fund_code.isdigit()

        # 用户数据
        faker = RealFaker()
        password = faker.password()
        user = UserFactory(password=password)
        username = user.username
        _user_inst = User.lookup(username)
        token = auth.token(username=username, password=password)
        _headers = {'Content-Type': 'application/json',
                    'Authorization': "Bearer " + token}
        # 添加自选
        collect_data = {'collection_type': settings.SupportCollectionsEnum.fund.dk_value, 'identify': fund_code}
        result = create_collection(client, _headers, collect_data)
        resp = result.json
        assert resp
        logger.info(resp)
        assert result.status_code == 200
        _col_id = resp.get('id')
        assert _col_id
        label_items = list()
        creator_id = _user_inst.id
        for _ in range(5):
            label = LabelOfCollectionFactory(creator_id=creator_id)
            _label_name = label.name
            _label_inst = LabelsOfCollection.label_of_user_by_name(creator_id, _label_name)
            _label_id = _label_inst.id
            label_items.append(_label_id)
        #  错误用户创建
        labels_data = {'labels': label_items}
        not_mine_result = self.patch_labels(client, headers=bearer_header, collection_id=_col_id, data=labels_data)
        assert not_mine_result.status_code == 403
        # 正确用户
        is_mine_result = self.patch_labels(client, headers=_headers, collection_id=_col_id, data=labels_data)
        assert is_mine_result.status_code == 205
        logger.info(f'====is_mine_result.json====={is_mine_result.json}====')
        is_mine_result_resp = is_mine_result.json
        labels = is_mine_result_resp.get('labels')
        assert labels
        ret_labels_id_list = [item.get('id') for item in labels]
        in_list = label_items.sort()
        out_list = ret_labels_id_list.sort()
        assert in_list == out_list

        # 新用户创建一个label
        user = UserFactory(password=password)
        username = user.username
        _other_user_inst = User.lookup(username)
        other_id = _other_user_inst.id
        label = LabelOfCollectionFactory(creator_id=other_id)
        _label_name = label.name
        _label_inst = LabelsOfCollection.label_of_user_by_name(other_id, _label_name)
        new_label_id = _label_inst.id
        label_items.append(new_label_id)
        # 测试用户提交数据中包含其他用户的label
        new_labels_data = {'labels': label_items}
        is_mine_collection_but_not_all_mine_labels_result = self.patch_labels(client, headers=_headers,
                                                                              collection_id=_col_id,
                                                                              data=new_labels_data)

        assert is_mine_collection_but_not_all_mine_labels_result.status_code == 400
        is_mine_collection_but_not_all_mine_labels_resp = is_mine_collection_but_not_all_mine_labels_result.json
        logger.info(f'is_mine_collection_but_not_all_mine_labels_resp{is_mine_collection_but_not_all_mine_labels_resp}')
        label_is_not_exist_err = UserInputError.LABEL_IS_NOT_EXIST_ERR
        assert '更新失败' in label_is_not_exist_err.msg
        error_code = is_mine_collection_but_not_all_mine_labels_resp.get('error_code')
        assert error_code == label_is_not_exist_err.code
        # 清空关联
        clear_data = {'labels': []}
        clear_mine_result = self.patch_labels(client, headers=_headers, collection_id=_col_id, data=clear_data)
        assert clear_mine_result.status_code == 205
        clear_mine_resp = clear_mine_result.json
        assert clear_mine_resp == clear_data
        logger.info(f'====clear_mine_result====={clear_mine_result.json}')


class TestLabelDetail:

    @staticmethod
    def delete_label(client, headers=None, label_id=None):
        _endpoint = endpoint_of_label(label_id)
        _result = client.delete(_endpoint, headers=headers)
        return _result

    @staticmethod
    def patch_label(client, headers=None, label_id=None, data=None):
        _endpoint = endpoint_of_label(label_id)
        if not data:
            data = dict()
        _result = client.patch(_endpoint, headers=headers, json=data)
        return _result

    @pytest.fixture(scope="function", autouse=True)
    def delete_labels_from_db(self, request):
        """
        删除collection
        :return:
        """

        request.addfinalizer(delete_all_labels)
        return 0

    def test_patch_label(self, client, auth, bearer_header):
        """
        更新指定label
        :param client:
        :param auth:
        :return:
        """
        faker = RealFaker()
        password = faker.password()
        user = UserFactory(password=password)
        username = user.username
        user_inst = User.lookup(username)
        user_id = user_inst.id
        _label_inst = LabelOfCollectionFactory(creator_id=user_id)
        _label_name = _label_inst.name
        _label_inst = LabelsOfCollection.label_of_user_by_name(user_id, _label_name)
        _label_id = _label_inst.id
        token = auth.token(username=username, password=password)
        _headers = {'Content-Type': 'application/json',
                    'Authorization': "Bearer " + token}
        # 不带参数，返回错误
        result = self.patch_label(client, _headers, _label_id)
        assert result.status_code != 200
        # 颜色参数不对
        _word = faker.word()
        new_name = _label_name + _word
        update_label_data = {
            'name': new_name,
            'color': _word,
        }
        result = self.patch_label(client, _headers, _label_id, data=update_label_data)
        assert result.status_code != 200
        # 参数正确
        _word = faker.word()
        new_name = _label_name + _word
        color = faker.color()
        update_label_data = {
            'name': new_name,
            'color': color,
        }
        patch_result = self.patch_label(client, _headers, _label_id, data=update_label_data)
        assert patch_result.status_code == 200
        resp = patch_result.json
        resp_name = resp.get('name')
        assert resp_name == new_name
        # 更新不是自己的label
        not_my_label_patch_result = self.patch_label(client, bearer_header, _label_id, data=update_label_data)
        assert not_my_label_patch_result.status_code == 403
        # 指向不存在的标签
        patch_result_404 = self.patch_label(client, _headers, _label_id + 1, data=update_label_data)
        assert patch_result_404.status_code == 404

    def test_delete_label(self, client, auth, bearer_header):
        label_data = {'name': 'YYDS', 'color': '#2ba245', 'desc': '那些神一样的基金！'}
        result = create_label(client, bearer_header, label_data)
        resp = result.json
        assert result.status_code == 200
        assert resp

        # 删除不是自己的label
        faker = RealFaker()
        password = faker.password()
        user = UserFactory(password=password)
        _inst_id = resp.get('id')
        assert _inst_id
        token = auth.token(username=user.username, password=password)
        _headers = {'Content-Type': 'application/json',
                    'Authorization': "Bearer " + token}
        not_mine_del_result = self.delete_label(client, _headers, _inst_id)
        assert not_mine_del_result.status_code == 403
        deny_delete_resp = not_mine_del_result.json
        error_msg = deny_delete_resp.get('message')
        error_code = deny_delete_resp.get('error_code')
        assert error_msg
        forbidden_delete_others_error = UserInputError.FORBIDDEN_DELETE_OTHERS_ERR
        assert '删除失败' in error_msg
        assert error_code == forbidden_delete_others_error.code

        # 删除刚才创建的
        del_result = self.delete_label(client, bearer_header, _inst_id)
        assert del_result.status_code == 204
        # 路由中不带id
        del_no_id_result = self.delete_label(client, bearer_header)
        assert del_no_id_result.status_code == 405

        # 删除不存在的
        not_exist_id = _inst_id + 1
        delete_no_data_result = self.delete_label(client, bearer_header, not_exist_id)
        assert delete_no_data_result.status_code == 404

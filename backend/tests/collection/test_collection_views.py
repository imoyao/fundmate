# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2023/1/5 22:10
# File : test_collection_views.py
import json
import random

from factory import Faker

import pytest
from faker import Faker as RealFaker

from backend.fundmate import settings
from backend.fundmate.collection.models import Collections
from backend.fundmate.errors import ClientError, UserInputError
from backend.fundmate.exts.flask_loguru import logger

from ..factories import FundFactory, UserFactory


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


def get_collection(client, headers=None, params=None):
    if not params:
        params = dict()
    #  get url 携带参数：https://stackoverflow.com/a/28056409
    _result = client.get("collections/", headers=headers, query_string=params)
    return _result


def create_collection(client, headers=None, data=None):
    if not data:
        data = dict()
    _result = client.post("collections/", headers=headers, json=data)
    return _result


def delete_collection(client, headers=None, data=None):
    if not data:
        data = dict()
    _result = client.delete("collections/", headers=headers, json=data)
    return _result


@pytest.fixture(scope="function", autouse=True)
def delete_collection_from_db(request):
    """
    删除collection
    :return:
    """

    def delete_all_collections():
        cols = Collections.query.all()
        if cols:
            for row in cols:
                col_id = row.id
                _inst = Collections.get_by_id(col_id)
                if _inst:
                    _inst.delete()

    request.addfinalizer(delete_all_collections)
    return 0


def test_get_collections(db, client, bearer_header, create_base_data):
    # auth required
    no_auth_result = get_collection(client)
    assert no_auth_result.status_code == 401
    # 数据为空
    no_data_result = get_collection(client, headers=bearer_header)
    no_data_resp = no_data_result.json
    assert 'Missing data for required field' in json.dumps(no_data_resp)

    # 数据库数据为空
    params = {'collection_type': settings.SupportCollectionsEnum.fund.dk_value}
    with_collection_type_result = get_collection(client, headers=bearer_header, params=params)
    assert with_collection_type_result.status_code == 404

    # 先创建数据然后再获取
    fund_list = create_base_data.get('fund')
    for fund_code in fund_list:
        collect_data = {'collection_type': settings.SupportCollectionsEnum.fund.dk_value, 'identify': fund_code}
        result = create_collection(client, bearer_header, collect_data)
        assert result.status_code == 200

    with_data_result = get_collection(client, headers=bearer_header, params=params)
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
    # 获取股票
    stock_params = {'collection_type': settings.SupportCollectionsEnum.stock.dk_value}
    stack_with_data_result = get_collection(client, headers=bearer_header, params=stock_params)
    assert stack_with_data_result.status_code != 200


def test_create_collections(client, bearer_header, create_base_data):
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
    assert re_fund_resp.get('error_code') == ClientError.HAS_COLLECTED_ERR.code

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


def test_delete_collections(client, auth, bearer_header, create_base_data):
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
    not_mine_del_result = delete_collection(client, _headers, delete_data)
    assert not_mine_del_result.status_code == 403
    deny_delete_resp = not_mine_del_result.json
    error_msg = deny_delete_resp.get('message')
    error_code = deny_delete_resp.get('error_code')
    assert error_msg
    forbidden_delete_others_collection_error = UserInputError.FORBIDDEN_DELETE_OTHERS_COLLECTION_ERR
    assert error_msg == forbidden_delete_others_collection_error.message
    assert error_code == forbidden_delete_others_collection_error.code

    # 删除刚才创建的
    assert _inst_id
    delete_data = {'id': _inst_id}
    del_result = delete_collection(client, bearer_header, delete_data)
    assert del_result.status_code == 204

    # 删除不存在的
    delete_no_data = {'id': _inst_id + 1}
    delete_no_data_result = delete_collection(client, bearer_header, delete_no_data)
    assert delete_no_data_result.status_code == 404

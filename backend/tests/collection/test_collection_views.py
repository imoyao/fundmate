# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2023/1/5 22:10
# File : test_collection_views.py
import json
import random

from factory import Faker

import pytest

from backend.fundmate.exts.flask_loguru import logger

from ...fundmate.errors import ClientError
from ..factories import FundFactory


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


def create_collection(client, data=None, headers=None):
    if not data:
        data = dict()
    _result = client.post("collections/", json=data, headers=headers)
    return _result


def test_get_collections(app, client, bearer_header, create_base_data):
    # auth required
    no_auth_result = get_collection(client)
    assert no_auth_result.status_code == 401
    # 数据为空
    no_data_result = get_collection(client, headers=bearer_header)
    no_data_resp = no_data_result.json
    assert 'Missing data for required field' in json.dumps(no_data_resp)
    # 数据库数据为空
    params = {'collection_type': 'fund'}
    with_collection_type_result = get_collection(client, headers=bearer_header, params=params)
    assert with_collection_type_result.status_code == 404


def test_create_collections(client, bearer_header, create_base_data):
    # 基金数据组装
    fund_list = create_base_data.get('fund')
    logger.info(f'{fund_list}')
    fund_code = random.choice(fund_list)
    assert fund_code.isdigit()
    collect_data = {'collection_type': 'fund', 'identify': fund_code}

    # 测试不带认证参数
    no_auth_result = create_collection(client)
    no_auth_resp = no_auth_result.json
    logger.info(no_auth_resp)
    assert no_auth_result.status_code == 401

    # 自选基金
    result = create_collection(client, collect_data, bearer_header)
    resp = result.json
    assert result.status_code == 200
    assert resp
    assert resp.get('id')

    # 测试重复自选基金
    re_create_fund_result = create_collection(client, collect_data, bearer_header)
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
    collect_data_404 = {'collection_type': 'fund', 'identify': _code_404}
    data_404_create_fund_result = create_collection(client, collect_data_404, bearer_header)
    data_404_fund_resp = data_404_create_fund_result.json
    assert data_404_create_fund_result.status_code == 400
    assert data_404_fund_resp.get('error_code') == ClientError.COLLECTION_ERR.code

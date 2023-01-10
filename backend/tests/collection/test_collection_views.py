# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2023/1/5 22:10
# File : test_collection_views.py
import random

import pytest

from backend.fundmate.exts.flask_loguru import logger

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


def test_create_collections(app, client, bearer_header, create_base_data):
    # 存在的基金测试
    fund_list = create_base_data.get('fund')
    logger.info(f'{fund_list}')
    fund_code = random.choice(fund_list)
    assert fund_code.isdigit()
    collect_data = {'collection_type': 'fund', 'identify': fund_code}
    logger.info(f'{collect_data}')
    result = client.post("collections/", json=collect_data, headers=bearer_header)
    resp = result.json
    logger.info(resp)
    assert result.status_code == 200
    assert resp
    assert resp.get('id')

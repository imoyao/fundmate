# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2023/1/5 22:10
# File : test_collection_views.py
from backend.fundmate.exts.flask_loguru import logger

from ..factories import FundFactory


def create_base_data():
    """
    # 如何造假数据？ https://testerhome.com/topics/17088
    添加自选时必须保证有一定的基础数据，然后才能去添加自选
    :return:
    """
    fund = FundFactory()
    logger.info(fund.name)


def test_create_fund():
    fund = FundFactory()
    logger.info(f'{fund.name},{fund.fund_code},{fund.full_name}')

# def test_create_collections(app, client):
#     result = client.post("collections/")
#     assert result

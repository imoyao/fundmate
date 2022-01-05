#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/16 11:09
@file: test_combination.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 测试好买基金组合接口
"""
from typing import Dict, List, Optional

import pytest

from backend.fundmate.data.howbuy.combination import Strategy


class TestStrategy:
    """
    以牛基宝（全股型）为例：
    https://trade.ehowbuy.com/newpig/index.html#/adviser/index?productCode=tzzhqgx
    """

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.sty = Strategy()

    # def test_list_all(self) -> Optional[List]:
    #     pass
    #
    # def is_success(self, response: dict) -> bool:
    #     return response and response.get('code') == '0000'
    #
    # def test_detail(self, code: str, plan_name: str, plan_desc: str) -> Optional[Dict]:
    #     pass
    #
    # def test_parse_trading_elements(self, trading_elements_list: list):
    #     pass
    #
    # def test_parse_page_data(self, per_page_data):
    #     pass
    #
    # def trade_history(self, code: str, page: int = 1):
    #     pass
    #
    # def pagination_trade_info(self, code: str) -> List:
    #     pass
    #
    # def parse_net_worth(self, code: str, size: int = 30, page: int = 1):
    #     pass

    @pytest.mark.parametrize('str_date,expected', [('20220104', '2022-01-04')])
    def test_datestr_to_isodatestr(self, str_date: str, expected: str):
        assert self.sty.datestr_to_isodatestr(str_date) == expected

    # def test_net_worth(self, code: str, size: int = 50, is_df=True) -> Optional[List]:
    #     pass

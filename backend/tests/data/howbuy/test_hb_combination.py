#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/16 11:09
@file: test_dj_combination.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 测试好买基金组合接口
"""
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

    @pytest.mark.parametrize('sty_code', ['zozh002', 'jytg002'])
    def test_get_choice_fund_pools(self, sty_code):
        assert self.sty.get_choice_fund_pools(sty_code)

    def test_newest_holds(self):
        assert self.sty.latest_holds('zozh002')

    def test_parse_net_worth(self):
        result = self.sty.parse_net_worth('zozh002')
        assert result
        assert isinstance(result, list)

    def test_sty_detail(self):
        assert self.sty.detail('zozh002')

    @pytest.mark.parametrize('str_date,expected', [('20220104', '2022-01-04')])
    def test_datestr_to_isodatestr(self, str_date: str, expected: str):
        assert self.sty.datestr_to_isodatestr(str_date) == expected

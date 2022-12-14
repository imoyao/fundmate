# -*- coding: utf-8 -*-
"""
@Time ： 2022/12/14 16:11
@File ：test_china_wealth.py
@IDE ：PyCharm
"""
from backend.fundmate.data.chinawealth.products import ChinaWealth
from backend.fundmate.types import PdDataFrame


class TestChinaWealth:
    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_cw = ChinaWealth()

    def test_agencies(self):
        result = self.test_cw.agencies()
        assert not result.empty
        assert result.columns.to_list() == ['dm', 'ms']
        assert isinstance(result, PdDataFrame)

    def test_products(self):
        result = self.test_cw.products()
        assert not result.empty
        assert isinstance(result, PdDataFrame)

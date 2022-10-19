#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/16 11:09
@file: test_combination.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 测试好买基金组合接口
"""
from backend.fundmate.data.qieman.combination import Strategy


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

    def test_get_latest_sign(self):
        result = self.sty.get_latest_sign()
        assert result
        assert len(result) == 45

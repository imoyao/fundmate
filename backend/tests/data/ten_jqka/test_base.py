#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/9/30 16:05
"""
对基础数据处理进行测试
"""
import pytest

from backend.fundmate.data.ten_jqka.base import FundInfo


class TestFFundInfo:

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_dj_f = FundInfo()

    @pytest.mark.parametrize('fund_code,expected', [('001718', '工银物流产业股票A')])
    def test_fund_name(self, fund_code, expected):
        assert self.test_dj_f.fund_name(fund_code) == expected

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/3/1 14:16
@file: test_base.py
@author: imoyao
@email: immoyao@gmail.com
@desc:
"""
import pytest

from backend.fundmate.data.dkhs.base import FundFeeRatio


class TestFundFeeRatio:

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_frt = FundFeeRatio()

    # FIXME: 需要调用数据库
    @pytest.mark.parametrize('fund_code,expected', [('163406', {
        'purchase': [{
            'start_quota': 0.0,
            'end_quota': 500000.0,
            'rate': 1.2,
            'fee_amount': None
        }, {
            'start_quota': 500000.0,
            'end_quota': 2000000.0,
            'rate': 0.8,
            'fee_amount': None
        }, {
            'start_quota': 2000000.0,
            'end_quota': 5000000.0,
            'rate': 0.5,
            'fee_amount': None
        }, {
            'start_quota': 5000000.0,
            'end_quota': None,
            'rate': 0.0,
            'fee_amount': 1000.0
        }],
        'redeem': [{
            'start_day': 0,
            'end_day': 7,
            'rate': 1.5,
            'fee_amount': None
        }, {
            'start_day': 7,
            'end_day': 365,
            'rate': 0.5,
            'fee_amount': None
        }, {
            'start_day': 365,
            'end_day': 730,
            'rate': 0.25,
            'fee_amount': None
        }, {
            'start_day': 730,
            'end_day': 0,
            'rate': 0.0,
            'fee_amount': None
        }]
    })])
    def test_rate(self, fund_code, expected):
        """
        测试费率获取功能
        :param fund_code:
        :param expected:
        :return:
        """
        assert self.test_frt.rate(fund_code) == expected

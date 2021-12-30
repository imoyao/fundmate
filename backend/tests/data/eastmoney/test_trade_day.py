#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/30 14:13
@file: test_trade_day.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 测试交易日
"""
from typing import Dict

import pytest

from backend.fundmate.data.eastmoney.trade_day import TradeDay


class TestTradeDay:

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.td = TradeDay()

    @pytest.mark.parametrize('f_code,is_buy,expected', [('163406', True, 1), ('163406', False, 1), ('118001', True, 2),
                                                        ('118001', False, 2)])
    def test_t_days(self, f_code: str, is_buy: bool, expected: int):
        assert self.td.t_days(f_code, is_buy) == expected

    @pytest.mark.parametrize(
        'fund_code, op_date, is_buy, is_after_15o_clock, expected',
        [('163406', '2021-12-30', True, True, {
            'application_date': '2021-12-31',
            'deadline': '2022-01-04',
            'is_same_day': False,
            'maturity': '2022-01-04'
        }),
         ('163406', '2021-12-30', False, True, {
             'application_date': '2021-12-31',
             'deadline': '2022-01-04',
             'is_same_day': False,
             'maturity': '2022-01-04'
         }),
         ('163406', '2021-12-30', True, False, {
             'application_date': '2021-12-30',
             'is_same_day': True,
             'maturity': '2021-12-31',
             'deadline': '2021-12-31'
         }),
         ('163406', '2021-12-30', False, False, {
             'application_date': '2021-12-30',
             'is_same_day': True,
             'maturity': '2021-12-31',
             'deadline': '2021-12-31'
         }),
         ('118001', '2021-12-30', True, True, {
             'application_date': '2021-12-31',
             'deadline': '2022-01-05',
             'is_same_day': False,
             'maturity': '2022-01-05'
         }),
         ('118001', '2021-12-30', False, True, {
             'application_date': '2021-12-31',
             'deadline': '2022-01-05',
             'is_same_day': False,
             'maturity': '2022-01-05'
         }),
         ('118001', '2021-12-30', True, False, {
             'application_date': '2021-12-30',
             'deadline': '2022-01-04',
             'is_same_day': True,
             'maturity': '2022-01-04'
         }),
         ('118001', '2021-12-30', False, False, {
             'application_date': '2021-12-30',
             'deadline': '2022-01-04',
             'is_same_day': True,
             'maturity': '2022-01-04'
         }),
         ('000710', '2021-12-29', True, True, {
             'application_date': '2021-12-30',
             'deadline': '2021-12-31',
             'is_same_day': False,
             'maturity': '2021-12-31'
         }),
         ('000710', '2021-12-29', False, True, {
             'application_date': '2021-12-30',
             'deadline': '2021-12-31',
             'is_same_day': False,
             'maturity': '2021-12-31'
         }),
         ('000710', '2021-12-29', True, False, {
             'application_date': '2021-12-29',
             'deadline': '2021-12-30',
             'is_same_day': True,
             'maturity': '2021-12-30'
         }),
         ('000710', '2021-12-29', False, False, {
             'application_date': '2021-12-29',
             'deadline': '2021-12-30',
             'is_same_day': True,
             'maturity': '2021-12-30'
         })],
    )
    def test_get_trade_info(self, fund_code: str, op_date: str, is_buy: bool, is_after_15o_clock: bool, expected: Dict):
        assert self.td.get_trade_info(fund_code, op_date, is_buy, is_after_15o_clock) == expected

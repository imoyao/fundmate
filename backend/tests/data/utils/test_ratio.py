#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/2/25 14:06
@file: test_ratio.py
@author: imoyao
@email: immoyao@gmail.com
@desc:
"""
import portion
import pytest

from backend.fundmate.data.utils import ratio
from backend.fundmate.excepts import IsClosedDurationError


class TestFundFeeRatio:
    """
    FIXME:一些需要特殊处理的基金
    000906：按照美元计算
    000507, 003663
    """

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_ratio = ratio.BaseRatio()

    @pytest.mark.parametrize('raw_str,expected', [('500.0万', 'w'), ('1个月', 'm'), ('2.0年', 'y'), ('7天', 'd'),
                                                  ('500.0万美元', 'wud'), ('500.0美元', 'ud'), ('500.0元', 'cy')])
    def test_re_mark_replace_flag(self, raw_str, expected):
        assert self.test_ratio.re_mark_replace_flag(raw_str) == expected

    @pytest.mark.parametrize('raw_str,expected', [('100.0万<=买入金额<500.0万', '100.0万≤买入金额<500.0万'),
                                                  ('持有期限 >= 1个月', '持有期限 ≥ 1个月'), ('foo＞bar', 'foo>bar'),
                                                  ('test＜baz', 'test<baz')])
    def test_replace_co_equality(self, raw_str, expected):
        assert self.test_ratio.replace_co_equality(raw_str) == expected

    @pytest.mark.parametrize('raw_str,expected', [('7天 ≤ 持有期限 < 1个月', ['7天', '持有期限', '1个月']),
                                                  ('100.0万<=买入金额<500.0万', ['100.0万', '买入金额', '500.0万']),
                                                  ('7天 ≤ 持有期限 < 30天', ['7天', '持有期限', '30天']),
                                                  ('持有期限 < 7天', ['持有期限', '7天']), ('持有期限 > 1个月', ['持有期限', '1个月']),
                                                  ('1个月 ≤ 持有期限 < 1年', ['1个月', '持有期限', '1年'])])
    def test_re_split_with_comparison_operators(self, raw_str, expected):
        assert self.test_ratio.re_split_with_comparison_operators(raw_str) == expected

    @pytest.mark.parametrize('redeem_rate,time_key,rate_key,expected', [([{
        'money': '',
        'time': '持有期限 < 7天',
        'source': '',
        'rate': '1.50%'
    }, {
        'money': '',
        'time': '7天 ≤ 持有期限 < 30天',
        'source': '',
        'rate': '0.75%'
    }, {
        'money': '',
        'time': '30天 ≤ 持有期限 < 6个月',
        'source': '',
        'rate': '0.50%'
    }, {
        'money': '',
        'time': '持有期限 ≥ 6个月',
        'source': '',
        'rate': '0.00%'
    }], 'time', 'rate', [{
        'end_day': 7,
        'rate': 1.5,
        'start_day': 0
    }, {
        'end_day': 30,
        'rate': 0.75,
        'start_day': 7
    }, {
        'end_day': 180,
        'rate': 0.5,
        'start_day': 30
    }, {
        'end_day': None,
        'rate': 0.0,
        'start_day': 180
    }])])
    def test_redeem_rate(self, redeem_rate, time_key, rate_key, expected):
        assert self.test_ratio.redeem_rate(redeem_rate, time_key, rate_key) == expected

    @pytest.mark.parametrize('suffix_str,replace_flag,expected', [('100万', 'w', 1000000), ('500.0万', 'w', 5000000),
                                                                  ('500.0万美元', 'wud', 5000000), ('500.0美元', 'ud', 500),
                                                                  ('500.0万', 'w', 5000000), ('50.0万', 'w', 500000),
                                                                  ('0.0万', 'w', 0), ('7.0天', 'd', 7), ('7天', 'd', 7),
                                                                  ('1个月', 'm', 30), ('2.0年', 'y', 730)])
    def test_suffix_str_to_num(self, suffix_str, replace_flag, expected):
        """
        :param suffix_str:
        :param replace_flag:
        :param expected:
        :return:
        """
        assert self.test_ratio.suffix_str_to_num(suffix_str, replace_flag) == expected

    @pytest.mark.parametrize('range_str_with_co,expected', [
        ('100万<x<500.0万', portion.closedopen(1000000.0, 5000000.0)),
        ('100万美元<x<500.0万美元', portion.closedopen(1000000.0, 5000000.0)),
        ('x>1万美元', portion.closedopen(10000.0, portion.inf)),
        ('x≥1万美元', portion.closedopen(10000.0, portion.inf)),
        ('7天≤x<30天', portion.closedopen(7, 30)),
        ('8天<x<30天', portion.closedopen(7, 30)),
        ('x<30天', portion.closedopen(0, 30)),
        ('x≤6天', portion.closedopen(0, 7)),
        ('7天≤x<1年', portion.closedopen(7, 365)),
        ('7天 ≤ 持有期限 ≤ 30天', portion.closedopen(7, 31)),
        ('持有期限 > 30天', portion.closedopen(31, portion.inf)),
        ('7天≤x≤1年', portion.closedopen(7, 366)),
        ('x>29天', portion.closedopen(30, portion.inf)),
        ('1年>x>31天', portion.closedopen(30, 365)),
        ('1年≥x≥31天', portion.closedopen(31, 366)),
        ('1年≥x≥30天', portion.closedopen(30, 366)),
        ('1年≥x>30天', portion.closedopen(31, 366)),
        ('1年>x≥1个月', portion.closedopen(30, 365)),
        ('x≥30天', portion.closedopen(30, portion.inf)),
        ('x>30天', portion.closedopen(31, portion.inf)),
        ('持有期限 < 7天', portion.closedopen(0, 7)),
        ('7 天≤T<1 个封闭期', IsClosedDurationError),
        ('7 日≤T<1 年', portion.closedopen(7, 365)),
        ('购买金额 ≥ 500万', portion.closedopen(5000000.0, portion.inf)),
    ])
    def test_parse_portion(self, range_str_with_co, expected):
        """
        :param range_str_with_co:
        :param expected:
        :return:
        """
        # see also: https://stackoverflow.com/questions/56870699/pytest-how-to-parametrize-when-some-values-should
        # -return-an-error
        if isinstance(expected, type) and issubclass(expected, Exception):
            with pytest.raises(expected):
                self.test_ratio.parse_portion(range_str_with_co)
        else:
            assert self.test_ratio.parse_portion(range_str_with_co) == expected

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/9/30 16:05
"""
对基础数据处理进行测试
"""
import pytest

from backend.fundmate.data.danjuan.base import FundFeeRatio


class TestFundFeeRatio:

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_dj_fr = FundFeeRatio()

    @pytest.mark.parametrize('suffix_str,replace_flag,expected', [('100万', 'w', 1000000), ('7.0天', 'd', 7),
                                                                  ('2.0年', 'n', 730)])
    def test_suffix_str_to_num(self, suffix_str, replace_flag, expected):
        """
        多个参数一次传入示例
        :param suffix_str:
        :param replace_flag:
        :param expected:
        :return:
        """
        assert self.test_dj_fr.suffix_str_to_num(suffix_str, replace_flag) == expected

    def test_parse_first(self):
        assert self.test_dj_fr.parse_first('买入金额<100.0万') == 1000000

    @pytest.mark.parametrize('qt_name,p_type,expected', [('100.0万<=买入金额<500.0万', 'q', [1000000.0, 5000000.0]),
                                                         ('0.0天<持有期限<30.0天', 'd', [0, 30]),
                                                         ("365.0天<=持有期限<2.0年", 'd', [365, 730]),
                                                         ("2.0年<=持有期限<3.0年", 'd', [730, 1095])])
    def test___parse_both_limit(self, qt_name, p_type, expected):
        assert self.test_dj_fr._parse_both_limit(qt_name, p_type) == expected

    def test_parse_middle(self):
        test_list = [{'name': '100.0万<=买入金额<500.0万', 'value': '1.2'}, {'name': '500.0万<=买入金额<1000.0万', 'value': '0.8'}]
        assert self.test_dj_fr.parse_middle(test_list) == [{
            'start_quota': 1000000.0,
            'end_quota': 5000000.0,
            'rate': 1.2
        }, {
            'start_quota': 5000000.0,
            'end_quota': 10000000.0,
            'rate': 0.8
        }]

    @pytest.mark.parametrize('range_str,replace_flag,split_signal,expected', [('1000.0万<=买入金额', 'w', '<=', 10000000.0),
                                                                              ('180.0天<=持有期限', 'd', '<=', 180)])
    def test_parse_last(self, range_str, replace_flag, split_signal, expected):
        assert self.test_dj_fr.parse_last(range_str, replace_flag, split_signal) == expected

    @pytest.mark.parametrize('dup_list,expected', [([{
        "name": "0.0天<持有期限<7.0天",
        "value": "1.5"
    }, {
        "name": "0.0天<持有期限<30.0天",
        "value": "0.5"
    }, {
        "name": "7.0天<=持有期限<30.0天",
        "value": "0.5"
    }, {
        "name": "30.0天<=持有期限",
        "value": "0.0"
    }, {
        "name": "30.0天<=持有期限",
        "value": "0.0"
    }], [{
        'name': '0.0天<持有期限<7.0天',
        'value': '1.5'
    }, {
        'name': '7.0天<=持有期限<30.0天',
        'value': '0.5'
    }, {
        'name': '30.0天<=持有期限',
        'value': '0.0'
    }])])
    def test_remove_duplicate_resort(self, dup_list, expected):
        assert self.test_dj_fr.remove_duplicate_resort(dup_list) == expected

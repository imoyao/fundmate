#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/2/22 14:26
@file: test_base.py
@author: imoyao
@email: immoyao@gmail.com
@desc:对韭圈儿爬取数据功能进行测试
"""
import pytest

from backend.fundmate.data.fundb.base import FundFeeRatio


class TestFundFeeRatio:
    """
    FIXME:一些需要特殊处理的基金
    000906：按照美元计算
    """

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_jq_fr = FundFeeRatio()

    @pytest.mark.parametrize('fund_code,expected', [('007471', {
        'purchase': [{
            'start_quota': 0,
            'end_quota': None,
            'fee_amount': 0.0
        }],
        'op': [{
            'name': '管理费率',
            'val': '1.10% (每年)'
        }, {
            'name': '托管费率',
            'val': '0.15% (每年)'
        }, {
            'name': '销售服务费率',
            'val': '0.40% (每年)'
        }],
        'redeem': [{
            'start_day': 0,
            'end_day': 7,
            'rate': 1.5
        }, {
            'start_day': 7,
            'end_day': 30,
            'rate': 0.5
        }, {
            'start_day': 30,
            'end_day': None,
            'rate': 0.0
        }]
    }),
                                                    ('163406', {
                                                        'purchase': [{
                                                            'start_quota': 0,
                                                            'end_quota': 500000.0,
                                                            'rate': 0.12
                                                        }, {
                                                            'start_quota': 500000.0,
                                                            'end_quota': 2000000.0,
                                                            'rate': 0.08
                                                        }, {
                                                            'start_quota': 2000000.0,
                                                            'end_quota': 5000000.0,
                                                            'rate': 0.05
                                                        }, {
                                                            'start_quota': 5000000.0,
                                                            'end_quota': None,
                                                            'fee_amount': 1000.0
                                                        }],
                                                        'op': [{
                                                            'name': '管理费率',
                                                            'val': '1.50% (每年)'
                                                        }, {
                                                            'name': '托管费率',
                                                            'val': '0.25% (每年)'
                                                        }, {
                                                            'name': '销售服务费率',
                                                            'val': '0.00% (每年)'
                                                        }],
                                                        'redeem': [{
                                                            'start_day': 0,
                                                            'end_day': 7,
                                                            'rate': 1.5
                                                        }, {
                                                            'start_day': 7,
                                                            'end_day': 365,
                                                            'rate': 0.5
                                                        }, {
                                                            'start_day': 365,
                                                            'end_day': 730,
                                                            'rate': 0.25
                                                        }, {
                                                            'start_day': 730,
                                                            'end_day': None,
                                                            'rate': 0.0
                                                        }]
                                                    })])
    def test_rate(self, fund_code, expected):
        """
        测试费率获取功能
        :param fund_code:
        :param expected:
        :return:
        """
        assert self.test_jq_fr.rate(fund_code) == expected

    @pytest.mark.parametrize('suffix_str,replace_flag,expected', [('100万', 'w', 1000000), ('7.0天', 'd', 7),
                                                                  ('1个月', 'm', 30), ('2.0年', 'n', 730)])
    def test_suffix_str_to_num(self, suffix_str, replace_flag, expected):
        """
        多个参数一次传入示例
        :param suffix_str:
        :param replace_flag:
        :param expected:
        :return:
        """
        assert self.test_jq_fr.suffix_str_to_num(suffix_str, replace_flag) == expected

    @pytest.mark.parametrize('suffix_str,expected', [('买入金额<100.0万', 1000000)])
    def test_parse_first(self, suffix_str, expected):
        assert self.test_jq_fr.parse_first(suffix_str) == expected

    @pytest.mark.parametrize('qt_name,p_type,expected', [('100.0万<=买入金额<500.0万', 'q', [1000000.0, 5000000.0]),
                                                         ('7天 ≤ 持有期限 < 1年', 'd', [7, 365]),
                                                         ('7天 ≤ 持有期限 < 1个月', 'd', [7, 30]),
                                                         ('7天 ≤ 持有期限 < 30天', 'd', [7, 30]),
                                                         ('1个月 ≤ 持有期限 < 1年', 'd', [30, 365]),
                                                         ('1个月<=持有期限<3个月', 'd', [30, 90]),
                                                         ('1年 ≤ 持有期限 < 2年', 'd', [365, 730])])
    def test___parse_both_limit(self, qt_name, p_type, expected):
        assert self.test_jq_fr._parse_both_limit(qt_name, p_type) == expected

    @pytest.mark.parametrize('test_str,expected', [('1.5%', 1.5)])
    def test_remove_percent(self, test_str, expected):
        assert self.test_jq_fr.remove_percent(test_str) == expected

    @pytest.mark.parametrize('mid_info,expected', [
        ([{
            'money': '',
            'time': '7天 ≤ 持有期限 < 1年',
            'source': '',
            'rate': '0.10%'
        }, {
            'money': '',
            'time': '1年 ≤ 持有期限 < 2年',
            'source': '',
            'rate': '0.05%'
        }], [{
            'start_day': 7,
            'end_day': 365,
            'rate': 0.1
        }, {
            'start_day': 365,
            'end_day': 730,
            'rate': 0.05
        }]),
        ([{
            'money': '',
            'time': '7天 ≤ 持有期限 < 30天',
            'source': '',
            'rate': '0.75%'
        }, {
            'money': '',
            'time': '30天 ≤ 持有期限 < 180天',
            'source': '',
            'rate': '0.50%'
        }, {
            'money': '',
            'time': '180天 ≤ 持有期限 < 365天',
            'source': '',
            'rate': '0.25%'
        }], [{
            'start_day': 7,
            'end_day': 30,
            'rate': 0.75
        }, {
            'start_day': 30,
            'end_day': 180,
            'rate': 0.5
        }, {
            'start_day': 180,
            'end_day': 365,
            'rate': 0.25
        }]),
    ])
    def test___parse_day_have_both(self, mid_info, expected):
        assert self.test_jq_fr._parse_day_have_both(mid_info) == expected

    @pytest.mark.parametrize('info,expected', [([{
        'money': '',
        'time': '持有期限 < 7天',
        'source': '',
        'rate': '1.50%'
    }, {
        'money': '',
        'time': '7天 ≤ 持有期限 < 1年',
        'source': '',
        'rate': '0.10%'
    }, {
        'money': '',
        'time': '1年 ≤ 持有期限 < 2年',
        'source': '',
        'rate': '0.05%'
    }, {
        'money': '',
        'time': '持有期限 ≥ 2年',
        'source': '',
        'rate': '0.00%'
    }], [{
        'start_day': 0,
        'end_day': 7,
        'rate': 1.5
    }, {
        'start_day': 7,
        'end_day': 365,
        'rate': 0.1
    }, {
        'start_day': 365,
        'end_day': 730,
        'rate': 0.05
    }, {
        'start_day': 730,
        'end_day': None,
        'rate': 0.0
    }]),
                                               ([{
                                                   'money': '',
                                                   'time': '持有期限 < 7天',
                                                   'source': '',
                                                   'rate': '1.50%'
                                               }, {
                                                   'money': '',
                                                   'time': '7天 ≤ 持有期限 < 1个月',
                                                   'source': '',
                                                   'rate': '0.10%'
                                               }, {
                                                   'money': '',
                                                   'time': '持有期限 ≥ 1个月',
                                                   'source': '',
                                                   'rate': '0.00%'
                                               }], [{
                                                   'start_day': 0,
                                                   'end_day': 7,
                                                   'rate': 1.5
                                               }, {
                                                   'start_day': 7,
                                                   'end_day': 30,
                                                   'rate': 0.1
                                               }, {
                                                   'start_day': 30,
                                                   'end_day': None,
                                                   'rate': 0.0
                                               }])])
    def test_withdraw_rate(self, info, expected):
        assert self.test_jq_fr.withdraw_rate(info) == expected

    @pytest.mark.parametrize('info, expected', [([{
        'money': '',
        'time': '',
        'source': '',
        'rate': '0.00%'
    }], [{
        'start_quota': 0,
        'end_quota': None,
        'fee_amount': 0.0
    }])])
    def test_declare_rate(self, info, expected):
        assert self.test_jq_fr.declare_rate(info) == expected

    @pytest.mark.parametrize('range_str,replace_flag,split_signal,expected', [('1000.0万<=买入金额', 'w', '<=', 10000000.0),
                                                                              ('持有期限 ≥ 1个月', 'm', '≥', 30),
                                                                              ('180.0天<=持有期限', 'd', '<=', 180)])
    def test_parse_last(self, range_str, replace_flag, split_signal, expected):
        assert self.test_jq_fr.parse_last(range_str, replace_flag, split_signal) == expected

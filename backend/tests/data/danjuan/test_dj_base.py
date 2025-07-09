#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/9/30 16:05
"""
对基础数据处理进行测试
"""
import portion
import pytest

from backend.fundmate.data.danjuan.base import DanJuanEvl, FundFeeRatio, FundInfo


class TestFundInfo:

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_dj_f = FundInfo()

    @pytest.mark.parametrize('fund_code,expected', [('660010', '农银汇理策略精选混合型证券投资基金')])
    def test_fund_full_name(self, fund_code, expected):
        assert self.test_dj_f.fund_full_name(fund_code) == expected


class TestDanJuanEvl:

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_dj_evl = DanJuanEvl()

    @pytest.mark.parametrize('channel', ['jiucai', 'lsd', None])
    def test_fund_full_name(self, channel):
        result = self.test_dj_evl.get_detail(channel)
        if channel:
            assert result
            assert result.get('result_code') == 0
            assert isinstance(result, dict)
        else:
            assert not result


class TestFundFeeRatio:

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_dj_fr = FundFeeRatio()

    @pytest.mark.parametrize('fund_code,expected', [('007471', None),
                                                    ('163406', {
                                                        'op': [{
                                                            'name': '基金托管费',
                                                            'value': '0.2500'
                                                        }, {
                                                            'name': '基金管理费',
                                                            'value': '1.5000'
                                                        }],
                                                        'purchase': [{
                                                            'end_quota': 500000.0,
                                                            'rate': 1.2,
                                                            'start_quota': 0
                                                        }, {
                                                            'end_quota': 2000000.0,
                                                            'rate': 0.8,
                                                            'start_quota': 500000.0
                                                        }, {
                                                            'end_quota': 5000000.0,
                                                            'rate': 0.5,
                                                            'start_quota': 2000000.0
                                                        }, {
                                                            'end_quota': None,
                                                            'fee_amount': 1000.0,
                                                            'start_quota': 5000000.0
                                                        }],
                                                        'redeem': [{
                                                            'end_day': 7,
                                                            'rate': 1.5,
                                                            'start_day': 0
                                                        }, {
                                                            'end_day': 365,
                                                            'rate': 0.5,
                                                            'start_day': 7
                                                        }, {
                                                            'end_day': 730,
                                                            'rate': 0.25,
                                                            'start_day': 365
                                                        }, {
                                                            'end_day': None,
                                                            'rate': 0.0,
                                                            'start_day': 730
                                                        }]
                                                    }),
                                                    ('007019', {
                                                        'op': [{
                                                            'name': '销售服务费',
                                                            'value': '0.3500'
                                                        }, {
                                                            'name': '基金托管费',
                                                            'value': '0.1000'
                                                        }, {
                                                            'name': '基金管理费',
                                                            'value': '0.3000'
                                                        }],
                                                        'purchase': [{
                                                            'end_quota': None,
                                                            'fee_amount': 0.0,
                                                            'start_quota': 0
                                                        }],
                                                        'redeem': [{
                                                            'end_day': 7,
                                                            'rate': 1.5,
                                                            'start_day': 0
                                                        }, {
                                                            'end_day': 31,
                                                            'rate': 0.1,
                                                            'start_day': 7
                                                        }, {
                                                            'end_day': None,
                                                            'rate': 0.0,
                                                            'start_day': 31
                                                        }]
                                                    }),
                                                    ('000906', {
                                                        'op': [{
                                                            'name': '基金托管费',
                                                            'value': '0.3500'
                                                        }, {
                                                            'name': '基金管理费',
                                                            'value': '1.8000'
                                                        }],
                                                        'purchase': [{
                                                            'end_quota': 200000.0,
                                                            'rate': 1.6,
                                                            'start_quota': 0
                                                        }, {
                                                            'end_quota': 1000000.0,
                                                            'rate': 1.0,
                                                            'start_quota': 200000.0
                                                        }, {
                                                            'end_quota': 2000000.0,
                                                            'rate': 0.5,
                                                            'start_quota': 1000000.0
                                                        }, {
                                                            'end_quota': None,
                                                            'fee_amount': 200.0,
                                                            'start_quota': 2000000.0
                                                        }],
                                                        'redeem': [{
                                                            'end_day': 7,
                                                            'rate': 1.5,
                                                            'start_day': 0
                                                        }, {
                                                            'end_day': 365,
                                                            'rate': 0.5,
                                                            'start_day': 7
                                                        }, {
                                                            'end_day': 730,
                                                            'rate': 0.3,
                                                            'start_day': 365
                                                        }, {
                                                            'end_day': None,
                                                            'rate': 0.0,
                                                            'start_day': 730
                                                        }]
                                                    }),
                                                    ('000507', {
                                                        'op': [{'name': '销售服务费', 'value': '0.0000'}, {
                                                            'name': '基金托管费',
                                                            'value': '0.2500'
                                                        }, {'name': '基金管理费',
                                                            'value': '0.6000'
                                                            }],
                                                        'purchase': [{
                                                            'end_quota': 500000.0,
                                                            'rate': 1.2,
                                                            'start_quota': 0
                                                        }, {
                                                            'end_quota': 1000000.0,
                                                            'rate': 1.0,
                                                            'start_quota': 500000.0
                                                        }, {
                                                            'end_quota': 3000000.0,
                                                            'rate': 0.8,
                                                            'start_quota': 1000000.0
                                                        }, {
                                                            'end_quota': 5000000.0,
                                                            'rate': 0.6,
                                                            'start_quota': 3000000.0
                                                        }, {
                                                            'end_quota': None,
                                                            'fee_amount': 1000.0,
                                                            'start_quota': 5000000.0
                                                        }],
                                                        'redeem': [{
                                                            'end_day': 7,
                                                            'rate': 1.5,
                                                            'start_day': 0
                                                        }, {
                                                            'end_day': 30,
                                                            'rate': 0.75,
                                                            'start_day': 7
                                                        }, {
                                                            'end_day': 90,
                                                            'rate': 0.5,
                                                            'start_day': 30
                                                        }, {
                                                            'end_day': 180,
                                                            'rate': 0.5,
                                                            'start_day': 90
                                                        }, {
                                                            'end_day': 366,
                                                            'rate': 0.1,
                                                            'start_day': 180
                                                        }, {
                                                            'end_day': 730,
                                                            'rate': 0.05,
                                                            'start_day': 366
                                                        }, {
                                                            'end_day': None,
                                                            'rate': 0.0,
                                                            'start_day': 730
                                                        }]
                                                    }),
                                                    ('003663', {
                                                        'op': [{
                                                            'name': '基金托管费',
                                                            'value': '0.2000'
                                                        }, {
                                                            'name': '基金管理费',
                                                            'value': '0.7000'
                                                        }],
                                                        'purchase': [{
                                                            'end_quota': 1000000.0,
                                                            'rate': 0.8,
                                                            'start_quota': 0
                                                        }, {
                                                            'end_quota': 5000000.0,
                                                            'rate': 0.4,
                                                            'start_quota': 1000000.0
                                                        }, {
                                                            'end_quota': None,
                                                            'fee_amount': 1000.0,
                                                            'start_quota': 5000000.0
                                                        }],
                                                        'redeem': [{
                                                            'end_day': 180,
                                                            'rate': 1.5,
                                                            'start_day': 0
                                                        }, {
                                                            'end_day': None,
                                                            'rate': 0.0,
                                                            'start_day': 180
                                                        }]
                                                    })])
    def test_rate(self, fund_code, expected):
        assert self.test_dj_fr.rate(fund_code) == expected

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
        ('30.0天<持有期限', portion.closedopen(31, portion.inf)),
        ('7天≤x≤1年', portion.closedopen(7, 366)),
        ('x>29天', portion.closedopen(30, portion.inf)),
        ('1年>x>31天', portion.closedopen(30, 365)),
        ('1年≥x≥31天', portion.closedopen(31, 366)),
        ('1年≥x≥30天', portion.closedopen(30, 366)),
        ('1年≥x>30天', portion.closedopen(31, 366)),
        ('1年>x≥1个月', portion.closedopen(30, 365)),
        ('x≥30天', portion.closedopen(30, portion.inf)),
        ('0.0万<买入金额', portion.closedopen(0, portion.inf)),
        ('购买金额 ≥ 500万', portion.closedopen(5000000.0, portion.inf)),
    ])
    def test_parse_portion(self, range_str_with_co, expected):
        """
        :param range_str_with_co:
        :param expected:
        :return:
        """
        assert self.test_dj_fr.parse_portion(range_str_with_co) == expected

    @pytest.mark.parametrize('dup_list,expected', [([{
        'name': '0.0天<持有期限<7.0天',
        'value': '1.5'
    }, {
        'name': '0.0天<持有期限<30.0天',
        'value': '0.5'
    }, {
        'name': '7.0天<=持有期限<30.0天',
        'value': '0.5'
    }, {
        'name': '30.0天<=持有期限',
        'value': '0.0'
    }, {
        'name': '30.0天<=持有期限',
        'value': '0.0'
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

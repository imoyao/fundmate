#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/2/22 14:26
@file: test_base.py
@author: imoyao
@email: immoyao@gmail.com
@desc:对韭圈儿爬取数据功能进行测试
"""

import random

import pytest
from backend.fundmate.data.fundb.base import FundDB, FundFeeRatio, IndustryEnum, fed_args
from backend.fundmate.excepts import CrawlerException, ParseError


class TestFundFeeRatio:
    """
    测试基金费率信息
    """

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_jq_fr = FundFeeRatio()

    @pytest.mark.parametrize(
        'fund_code,expected',
        [
            (
                '007471',
                {
                    'purchase': [{'start_quota': 0, 'end_quota': None, 'fee_amount': 0.0}],
                    'op': [
                        {'name': '管理费率', 'val': '1.10% (每年)'},
                        {'name': '托管费率', 'val': '0.15% (每年)'},
                        {'name': '销售服务费率', 'val': '0.40% (每年)'},
                    ],
                    'redeem': [
                        {'start_day': 0, 'end_day': 7, 'rate': 1.5},
                        {'start_day': 7, 'end_day': 30, 'rate': 0.5},
                        {'start_day': 30, 'end_day': None, 'rate': 0.0},
                    ],
                },
            ),
            (
                '163406',
                {
                    'purchase': [
                        {'start_quota': 0, 'end_quota': 500000.0, 'rate': 1.2},
                        {'start_quota': 500000.0, 'end_quota': 2000000.0, 'rate': 0.8},
                        {'start_quota': 2000000.0, 'end_quota': 5000000.0, 'rate': 0.5},
                        {'start_quota': 5000000.0, 'end_quota': None, 'fee_amount': 1000.0},
                    ],
                    'op': [
                        {'name': '管理费率', 'val': '1.50% (每年)'},
                        {'name': '托管费率', 'val': '0.25% (每年)'},
                        {'name': '销售服务费率', 'val': '0.00% (每年)'},
                    ],
                    'redeem': [
                        {'start_day': 0, 'end_day': 7, 'rate': 1.5},
                        {'start_day': 7, 'end_day': 365, 'rate': 0.5},
                        {'start_day': 365, 'end_day': 730, 'rate': 0.25},
                        {'start_day': 730, 'end_day': None, 'rate': 0.0},
                    ],
                },
            ),
            (
                '850004',
                {
                    'op': [
                        {'name': '管理费率', 'val': '0.70% (每年)'},
                        {'name': '托管费率', 'val': '0.15% (每年)'},
                        {'name': '销售服务费率', 'val': '0.00% (每年)'},
                    ],
                    'purchase': [{'end_quota': None, 'fee_amount': 0.0, 'start_quota': 0}],
                    'redeem': [
                        {'end_day': 7, 'rate': 1.5, 'start_day': 0},
                        {'end_day': 30, 'rate': 0.75, 'start_day': 7},
                        {'end_day': 365, 'rate': 0.5, 'start_day': 30},
                        {'end_day': None, 'rate': 0.0, 'start_day': 365},
                    ],
                },
            ),
            (
                '007019',
                {
                    'purchase': [{'start_quota': 0, 'end_quota': None, 'fee_amount': 0.0}],
                    'op': [
                        {'name': '管理费率', 'val': '0.30% (每年)'},
                        {'name': '托管费率', 'val': '0.10% (每年)'},
                        {'name': '销售服务费率', 'val': '0.35% (每年)'},
                    ],
                    'redeem': [
                        {'start_day': 0, 'end_day': 7, 'rate': 1.5},
                        {'start_day': 7, 'end_day': 31, 'rate': 0.1},
                        {'start_day': 31, 'end_day': None, 'rate': 0.0},
                    ],
                },
            ),
            (
                '000906',
                {
                    'op': [
                        {'name': '管理费率', 'val': '1.80% (每年)'},
                        {'name': '托管费率', 'val': '0.35% (每年)'},
                        {'name': '销售服务费率', 'val': '0.00% (每年)'},
                    ],
                    'purchase': [
                        {'end_quota': 200000.0, 'rate': 1.6, 'start_quota': 0},
                        {'end_quota': 1000000.0, 'rate': 1.0, 'start_quota': 200000.0},
                        {'end_quota': 2000000.0, 'rate': 0.5, 'start_quota': 1000000.0},
                        {'end_quota': None, 'fee_amount': 200.0, 'start_quota': 2000000.0},
                    ],
                    'redeem': [
                        {'end_day': 7, 'rate': 1.5, 'start_day': 0},
                        {'end_day': 365, 'rate': 0.5, 'start_day': 7},
                        {'end_day': 730, 'rate': 0.3, 'start_day': 365},
                        {'end_day': None, 'rate': 0.0, 'start_day': 730},
                    ],
                },
            ),
            (
                '000507',
                {
                    'op': [
                        {'name': '管理费率', 'val': '0.60% (每年)'},
                        {'name': '托管费率', 'val': '0.25% (每年)'},
                        {'name': '销售服务费率', 'val': '0.00% (每年)'},
                    ],
                    'purchase': [
                        {'end_quota': 500000.0, 'rate': 1.2, 'start_quota': 0},
                        {'end_quota': 1000000.0, 'rate': 1.0, 'start_quota': 500000.0},
                        {'end_quota': 3000000.0, 'rate': 0.8, 'start_quota': 1000000.0},
                        {'end_quota': 5000000.0, 'rate': 0.6, 'start_quota': 3000000.0},
                        {'end_quota': None, 'fee_amount': 1000.0, 'start_quota': 5000000.0},
                    ],
                    'redeem': [
                        {'end_day': 7, 'rate': 1.5, 'start_day': 1},
                        {'end_day': 30, 'rate': 0.75, 'start_day': 7},
                        {'end_day': 180, 'rate': 0.5, 'start_day': 30},
                        {'end_day': 366, 'rate': 0.1, 'start_day': 180},
                        {'end_day': 731, 'rate': 0.05, 'start_day': 366},
                        {'end_day': None, 'rate': 0.0, 'start_day': 731},
                    ],
                },
            ),
            (
                '007450',
                {
                    'op': [
                        {'name': '管理费率', 'val': '1.50% (每年)'},
                        {'name': '托管费率', 'val': '0.25% (每年)'},
                        {'name': '销售服务费率', 'val': '0.60% (每年)'},
                    ],
                    'purchase': [{'end_quota': None, 'fee_amount': 0.0, 'start_quota': 0}],
                    'redeem': [
                        {'end_day': 7, 'rate': 1.5, 'start_day': 0},
                        {'end_day': 30, 'rate': 0.5, 'start_day': 7},
                        {'end_day': None, 'rate': 0.0, 'start_day': 30},
                    ],
                },
            ),
            (
                '011779',
                {
                    'op': [
                        {'name': '管理费率', 'val': '0.55% (每年)'},
                        {'name': '托管费率', 'val': '0.10% (每年)'},
                        {'name': '销售服务费率', 'val': '0.00% (每年)'},
                    ],
                    'purchase': [
                        {'end_quota': 1000000.0, 'rate': 0.8, 'start_quota': 0},
                        {'end_quota': 2000000.0, 'rate': 0.4, 'start_quota': 1000000.0},
                        {'end_quota': 5000000.0, 'rate': 0.2, 'start_quota': 2000000.0},
                        {'end_quota': None, 'fee_amount': 1000.0, 'start_quota': 5000000.0},
                    ],
                    'redeem': [{'end_day': None, 'rate': 0.0, 'start_day': 0}],
                },
            ),
            (
                '003663',
                {
                    'op': [
                        {'name': '管理费率', 'val': '0.70% (每年)'},
                        {'name': '托管费率', 'val': '0.20% (每年)'},
                        {'name': '销售服务费率', 'val': '0.00% (每年)'},
                    ],
                    'purchase': [
                        {'end_quota': 1000000.0, 'rate': 0.8, 'start_quota': 0},
                        {'end_quota': 5000000.0, 'rate': 0.4, 'start_quota': 1000000.0},
                        {'end_quota': None, 'fee_amount': 1000.0, 'start_quota': 5000000.0},
                    ],
                    'redeem': [
                        {'end_day': 180, 'rate': 1.5, 'start_day': 0},
                        {'end_day': None, 'rate': 0.0, 'start_day': 180},
                    ],
                },
            ),
        ],
    )
    def test_rate(self, fund_code, expected):
        """
        测试费率获取功能
        :param fund_code:
        :param expected:
        :return:
        """
        # 可能会有预料不到的错误 [python - How to properly assert that an exception gets raised in pytest? - Stack Overflow](
        # https://stackoverflow.com/questions/23337471/how-to-properly-assert-that-an-exception-gets-raised-in-pytest)
        try:
            assert self.test_jq_fr.rate(fund_code) == expected
        except CrawlerException:
            assert True

    @pytest.mark.parametrize(
        'suffix_str,replace_flag,expected',
        [('100万', 'w', 1000000), ('7.0天', 'd', 7), ('1个月', 'm', 30), ('2.0年', 'y', 730)],
    )
    def test_suffix_str_to_num(self, suffix_str, replace_flag, expected):
        """
        多个参数一次传入示例
        :param suffix_str:
        :param replace_flag:
        :param expected:
        :return:
        """
        assert self.test_jq_fr.suffix_str_to_num(suffix_str, replace_flag) == expected

    @pytest.mark.parametrize('test_str,expected', [('1.5%', 1.5)])
    def test_remove_percent(self, test_str, expected):
        assert self.test_jq_fr.remove_percent(test_str) == expected

    @pytest.mark.parametrize(
        'info,expected',
        [
            (
                [
                    {'money': '', 'time': '持有期限 < 7天', 'source': '', 'rate': '1.50%'},
                    {'money': '', 'time': '7天 ≤ 持有期限 < 1年', 'source': '', 'rate': '0.10%'},
                    {'money': '', 'time': '1年 ≤ 持有期限 < 2年', 'source': '', 'rate': '0.05%'},
                    {'money': '', 'time': '持有期限 ≥ 2年', 'source': '', 'rate': '0.00%'},
                ],
                [
                    {'start_day': 0, 'end_day': 7, 'rate': 1.5},
                    {'start_day': 7, 'end_day': 365, 'rate': 0.1},
                    {'start_day': 365, 'end_day': 730, 'rate': 0.05},
                    {'start_day': 730, 'end_day': None, 'rate': 0.0},
                ],
            ),
            (
                [
                    {'money': '', 'time': '持有期限 < 7天', 'source': '', 'rate': '1.50%'},
                    {'money': '', 'time': '7天 ≤ 持有期限 < 1个月', 'source': '', 'rate': '0.10%'},
                    {'money': '', 'time': '持有期限 ≥ 1个月', 'source': '', 'rate': '0.00%'},
                ],
                [
                    {'start_day': 0, 'end_day': 7, 'rate': 1.5},
                    {'start_day': 7, 'end_day': 30, 'rate': 0.1},
                    {'start_day': 30, 'end_day': None, 'rate': 0.0},
                ],
            ),
            (
                [
                    {'money': '', 'time': '持有期限(Y) 赎回费率\r\nY<7日 1.50%', 'source': '', 'rate': '1.50%'},
                    {
                        'money': '',
                        'time': '持有期限(Y) 赎回费率\r\n7日≤Y<1个封闭期 1.00%',
                        'source': '',
                        'rate': '1.00%',
                    },
                    {'money': '', 'time': '持有期限(Y) 赎回费率\r\nY≥1个封闭期 0', 'source': '', 'rate': '0.00%'},
                ],
                ParseError,
            ),
        ],
    )
    def test_redeem_rate(self, info, expected):
        if isinstance(expected, type) and issubclass(expected, Exception):
            with pytest.raises(expected):
                self.test_jq_fr.redeem_rate(info)
        else:
            assert self.test_jq_fr.redeem_rate(info) == expected

    @pytest.mark.parametrize(
        'info,money_key,rate_key, expected',
        [
            (
                [{'money': '', 'time': '', 'source': '', 'rate': '0.00%'}],
                'money',
                'rate',
                [{'start_quota': 0, 'end_quota': None, 'fee_amount': 0.0}],
            ),
            (
                [
                    {'money': '购买金额 < 100万', 'time': '', 'source': '1.50%', 'rate': '0.15%'},
                    {'money': '100万 ≤ 购买金额 < 500万', 'time': '', 'source': '1.20%', 'rate': '0.12%'},
                    {'money': '购买金额 ≥ 500万', 'time': '', 'source': '1.00%', 'rate': '0.10%'},
                ],
                'money',
                'rate',
                [
                    {'start_quota': 0, 'end_quota': 1000000.0, 'rate': 1.5},
                    {'start_quota': 1000000.0, 'end_quota': 5000000.0, 'rate': 1.2},
                    {'start_quota': 5000000.0, 'end_quota': None, 'rate': 1.0},
                ],
            ),
            (
                [
                    {'money': '购买金额 < 10万美元', 'time': '', 'source': '', 'rate': '1.30%'},
                    {'money': '10万美元 ≤ 购买金额 < 20万美元', 'time': '', 'source': '', 'rate': '0.70%'},
                    {'money': '20万美元 ≤ 购买金额 < 100万美元', 'time': '', 'source': '', 'rate': '0.30%'},
                    {'money': '购买金额 ≥ 100万美元', 'time': '', 'source': '', 'rate': '200美元/笔'},
                ],
                'money',
                'rate',
                [
                    {'end_quota': 100000.0, 'rate': 1.3, 'start_quota': 0},
                    {'end_quota': 200000.0, 'rate': 0.7, 'start_quota': 100000.0},
                    {'end_quota': 1000000.0, 'rate': 0.3, 'start_quota': 200000.0},
                    {'end_quota': None, 'fee_amount': 200.0, 'start_quota': 1000000.0},
                ],
            ),
            (
                [
                    {'money': '购买金额 < 120万港元', 'time': '', 'source': '', 'rate': '1.60%'},
                    {'money': '120万港元 ≤ 购买金额 < 350万港元', 'time': '', 'source': '', 'rate': '1.00%'},
                    {'money': '350万港元 ≤ 购买金额 < 600万港元', 'time': '', 'source': '', 'rate': '0.80%'},
                    {'money': '购买金额 ≥ 600万港元', 'time': '', 'source': '', 'rate': '1200港元/笔'},
                ],
                'money',
                'rate',
                [
                    {'end_quota': 1200000.0, 'rate': 1.6, 'start_quota': 0},
                    {'end_quota': 3500000.0, 'rate': 1.0, 'start_quota': 1200000.0},
                    {'end_quota': 6000000.0, 'rate': 0.8, 'start_quota': 3500000.0},
                    {'end_quota': None, 'fee_amount': 1200.0, 'start_quota': 6000000.0},
                ],
            ),
        ],
    )
    def test_purchase_rate(self, info, money_key, rate_key, expected):
        assert self.test_jq_fr.purchase_rate(info, money_key, rate_key) == expected


class TestFundDB:
    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_jq_base = FundDB()

    def test_kjtl(self):
        result = self.test_jq_base.kjtl()
        assert result

    get_random_enum = random.choice(list(IndustryEnum))

    @pytest.mark.parametrize('kt_type,is_full', [(get_random_enum, False), (get_random_enum, True)])
    def test_industry(self, kt_type, is_full):
        result = self.test_jq_base.industry(kt_type, is_full)
        if result:
            status_str = result.get('status_str')
            num = result.get('num')
            assert status_str and isinstance(status_str, str)
            assert num and isinstance(num, int)
            assert result

    def test_emotion(self):
        full_info = self.test_jq_base.emotion(is_full=True)
        not_full_info = self.test_jq_base.emotion(is_full=True)
        assert full_info
        assert not_full_info

    @pytest.mark.xfail(reason='这个用例中校验接口请求的混淆参数，目前无法正确获取数据！')
    def test_fed(self):
        result = self.test_jq_base.fed()
        assert result


@pytest.mark.parametrize(
    'type_str,version,act_time,excepted',
    [
        (
            'pc',
            '2.2.7',
            1669977368593,
            {
                'abiokytke': '96',
                'act_time': 1669977368593,
                'bd24y6421f': '0a',
                'bd4uy742': '2',
                'bgd7h8tyu54': '00',
                'bgiuytkw': 'e4',
                'bioduytlw': 'b',
                'bvytikwqjk': '00',
                'fjlkatj': '09c',
                'ghtoiutkmlg': '888',
                'h13ey474': '323',
                'h67456y': 'dfe',
                'hy5641d321t': 'a2',
                'ibvytiqjek': '54',
                'iogojti': 'a',
                'jnhf8u5231': 'e4',
                'kf54ge7': '3',
                'lksytkjh': 'fe46',
                'n3bf4uj7y7': 'e',
                'nbf4uj7y432': '96',
                'nd354uy4752': '2',
                'ngd4uy551': 'fe',
                'ngd4yut78': '88',
                'nkjhrew': '2',
                'quikgdky': 'bd',
                'sbnoywr': '40',
                'tbvdiuytk': 'd',
                'tiklsktr4': 'd',
                'tirgkjfs': '7d',
                'type': 'pc',
                'u54rg5d': '09',
                'version': '2.2.7',
                'y654b5fs3tr': '8',
                'yi854tew': '32',
                'yt447e13f': '3',
            },
        )
    ],
)
def test_fed_args(type_str, version, act_time, excepted):
    result = fed_args(type_str, version, act_time)
    assert result == excepted
    assert result

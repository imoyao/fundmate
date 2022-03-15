#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/3/10 16:46
@file: test_base.py
@author: imoyao
@email: immoyao@gmail.com
@desc:
"""
import pytest

from backend.fundmate.data.eastmoney.base import EastMoney


class TestEastMoney:

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_em = EastMoney()

    # FIXME: 必须在数据库上下文中才可以测试
    @pytest.mark.parametrize('fund_code,expected', [('001718', {
        'create_time': '2016-03-01',
        'full_name': '工银瑞信物流产业股票型证券投资基金',
        'name': '工银物流产业股票A',
        'is_fe_charge_mode': True,
        'perf_comp_base': '沪深300运输指数收益率*80%+中债综合财富(总值)指数收益率*20%'
    }),
                                                    ('000033', {
                                                        'create_time': '2013-04-24',
                                                        'full_name': '易方达信用债债券型证券投资基金',
                                                        'is_fe_charge_mode': True,
                                                        'name': '易方达信用债债券C',
                                                        'perf_comp_base': '中债-信用债总指数'
                                                    }),
                                                    ('000002', {
                                                        'create_time': '2001-12-18',
                                                        'full_name': '华夏成长证券投资基金',
                                                        'is_fe_charge_mode': False,
                                                        'name': '华夏成长混合',
                                                        'perf_comp_base': '该基金暂未披露业绩比较基准'
                                                    })])
    def test_fund_base_info(self, fund_code, expected):
        assert self.test_em.fund_base_info(fund_code) == expected

    @pytest.mark.parametrize('mode_str,expected', [('001718（前端）', True), ('000002（后端）', False)])
    def test_match_charge_mode(self, mode_str, expected):
        assert self.test_em.match_charge_mode(mode_str) == expected

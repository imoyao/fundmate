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
from backend.fundmate.fund.models import FundType


def test_type(app):  # 传入参数request 系统封装参数
    ft = FundType.create(var_id=1, name='偏股')
    ft.save()
    ft = FundType.query.filter_by(id=1).one_or_none()
    assert ft.name


class TestEastMoney:

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_em = EastMoney()

    # FIXME: 必须在数据库上下文中才可以测试，f_var，f_type，co_id会变化
    @pytest.mark.parametrize('fund_code,expected', [('001718', {
        'full_name': '工银瑞信物流产业股票型证券投资基金',
        'name': '工银物流产业股票A',
        'perf_comp_base': '沪深300运输指数收益率*80%+中债综合财富(总值)指数收益率*20%',
        'company': '工银瑞信基金',
        'create_time': '2016-03-01',
        'f_var_name': '股票型',
        'f_type_name': None,
        'is_fe_charge_mode': True,
        'f_var': 6,
        'f_type': None,
        'co_id': 51
    }), ('000033', {
        'full_name': '易方达信用债债券型证券投资基金',
        'name': '易方达信用债债券C',
        'perf_comp_base': '中债-信用债总指数',
        'company': '易方达基金',
        'create_time': '2013-04-24',
        'f_var_name': '债券型',
        'f_type_name': '长债',
        'is_fe_charge_mode': True,
        'f_var': 2,
        'f_type': 3,
        'co_id': 12
    }), ('004750', {
        'full_name': '建信结算宝货币市场基金',
        'name': '建信结算宝货币',
        'perf_comp_base': '七天通知存款利率(税前)',
        'company': '建信基金',
        'create_time': None,
        'f_var_name': '货币型',
        'f_type_name': None,
        'is_fe_charge_mode': True,
        'f_var': 4,
        'f_type': None,
        'co_id': 54
    }), ('000002', {
        'full_name': '华夏成长证券投资基金',
        'name': '华夏成长混合',
        'perf_comp_base': '该基金暂未披露业绩比较基准',
        'company': '华夏基金',
        'create_time': '2001-12-18',
        'f_var_name': '混合型',
        'f_type_name': '偏股',
        'is_fe_charge_mode': False,
        'f_var': 1,
        'f_type': 1,
        'co_id': 5
    })])
    def test_fund_base_info(self, app, db, fund_code, expected):
        with app.app_context():
            assert self.test_em.fund_base_info(fund_code) == expected

    @pytest.mark.parametrize('mode_str,expected', [('001718（前端）', True), ('000002（后端）', False)])
    def test_match_charge_mode(self, mode_str, expected):
        assert self.test_em.match_charge_mode(mode_str) == expected

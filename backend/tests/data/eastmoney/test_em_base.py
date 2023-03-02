#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/3/10 16:46
@file: test_em_base.py
@author: imoyao
@email: immoyao@gmail.com
@desc:
"""
import pytest

from backend.fundmate.data.eastmoney.base import EastMoney
from backend.fundmate.fund.models import FundCompany, FundType, FundVariety


class TestEastMoney:

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_em = EastMoney()

    @pytest.fixture(scope='class')
    def create_base_fund_info_data(self, app, db):
        with app.app_context():
            vn1 = '股票型'
            fv1 = FundVariety.create(name=vn1).id
            vn2 = '债券型'
            fv2 = FundVariety.create(name=vn2).id
            vn3 = '混合型'
            fv3 = FundVariety.create(name=vn3).id
            FundType.create(var_id=fv1, name='一般股票型')
            FundType.create(var_id=fv2, name='长债')
            FundType.create(var_id=fv3, name='灵活')
            FundType.create(var_id=fv3, name='偏股')

    @pytest.mark.usefixtures("create_base_fund_info_data")      # 使用预制数据
    @pytest.mark.parametrize('fund_code,expected', [('001718', {
        'full_name': '工银瑞信物流产业股票型证券投资基金',
        'name': '工银物流产业股票A',
        'perf_comp_base': '沪深300运输指数收益率*80%+中债综合财富(总值)指数收益率*20%',
        'company': '工银瑞信基金',
        'create_time': '2016-03-01',
        'f_var_name': '股票型',
        'f_type_name': None,
        'is_fe_charge_mode': True,
        'f_type': None,
    }), ('000033', {
        'full_name': '易方达信用债债券型证券投资基金',
        'name': '易方达信用债债券C',
        'perf_comp_base': '中债-优选投资级信用债财富指数',
        'company': '易方达基金',
        'create_time': '2013-04-24',
        'f_var_name': '债券型',
        'f_type_name': '长债',
        'is_fe_charge_mode': True,
    }), ('004750', {
        'company': '广发基金',
        'create_time': '2018-01-16',
        'f_type_name': '灵活',
        'f_var_name': '混合型',
        'full_name': '广发鑫和灵活配置混合型证券投资基金',
        'is_fe_charge_mode': True,
        'name': '广发鑫和灵活配置混合A',
        'perf_comp_base': '沪深300指数收益率×30%+中证全债指数收益率×70%'
    }), ('000002', {
        'full_name': '华夏成长证券投资基金',
        'name': '华夏成长混合',
        'perf_comp_base': '该基金暂未披露业绩比较基准',
        'company': '华夏基金',
        'create_time': '2001-12-18',
        'f_var_name': '混合型',
        'f_type_name': '灵活',
        'is_fe_charge_mode': False,
    })])
    def test_fund_base_info(self, fund_code, expected):
        company_name = expected.get('company')
        company_id = FundCompany.id_by_name(company_name)
        expected['co_id'] = company_id
        f_var_name = expected.get('f_var_name')
        f_var = FundVariety.id_by_name(f_var_name)
        expected['f_var'] = f_var
        f_type_name = expected.get('f_type_name')
        f_type = FundType.id_by_name(f_type_name)
        expected['f_type'] = f_type
        assert self.test_em.fund_base_info(fund_code) == expected

    def test_company(self):
        result = self.test_em.company()
        assert result

    @pytest.mark.parametrize('company_info_seq', [(['80000222', '华夏基金管理有限公司', '1998-04-09', '589', '李一梅',
                                                    'HXJJ', '', '10910.98', '★★★★', '华夏基金', '5',
                                                    '2022/11/29 0:00:00'])])
    def test_save_company_to_db(self, app, db, company_info_seq):
        with app.app_context():
            result = self.test_em.save_company_to_db(company_info_seq)
            assert result and isinstance(result, FundCompany)

    @pytest.mark.parametrize('mode_str,expected', [('001718（前端）', True), ('000002（后端）', False)])
    def test_match_charge_mode(self, mode_str, expected):
        assert self.test_em.match_charge_mode(mode_str) == expected

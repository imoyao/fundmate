# -*- coding: utf-8 -*-
"""
@Time ： 2022/10/12 11:54
@File ：test_qgg_base.py
@IDE ：PyCharm
"""
import pytest

from backend.fundmate.data.zo.base import FollowAip, Strategy


class TestStrategy:
    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_sty = Strategy()

    def test_latest_info(self):
        result = self.test_sty.latest_info()
        assert result
        assert result.get('name') == '超级股票全明星'


class TestFundFollowAip:
    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_fa = FollowAip()

    @pytest.mark.parametrize('params,expected',
                             [('some_database_field_name', 'someDatabaseFieldName'),
                              ('Some label that needs to be caramelized', 'someLabelThatNeedsToBeCaramelized'),
                              ('some-javascript-property', 'someJavascriptProperty'),
                              ('some-mixed_string with spaces_underscores-and-hyphens',
                               'someMixedStringWithSpacesUnderscoresAndHyphens'),
                              ])
    def test_to_camel(self, params, expected):
        """
        测试费率获取功能
        :param params:
        :param expected:
        :return:
        """
        assert self.test_fa.to_camel(params) == expected

    @pytest.mark.parametrize('endpoint',
                             FollowAip.ENDPOINT_LIST)
    def test_sample_result(self, endpoint):
        """
        测试费率获取功能
        :param endpoint:
        :return:
        """
        assert self.test_fa.sample_result(endpoint)

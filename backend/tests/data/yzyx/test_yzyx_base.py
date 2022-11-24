# -*- coding: utf-8 -*-
"""
@Time ： 2022/11/23 17:42
@File ：test_yzyx_base.py
@IDE ：PyCharm
"""
import os

import pytest

from backend.fundmate.data.yzyx.base import YZYX
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.types import PdDataFrame


class TestYZYX:
    """
    测试基金费率信息
    """

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_yzyx = YZYX()

    @pytest.mark.parametrize('fp', ['test.html'])
    def test_get_html_text(self, fp):
        result = self.test_yzyx.get_html_text(html_fp=fp)
        assert result
        os.unlink(fp)

    @pytest.mark.parametrize('is_df', [True, False])
    def test_valuations(self, is_df):
        result = self.test_yzyx.valuations(is_df=is_df)
        result_keys = {'index_temper', 'interval_rate', 'yield', 'index_name', 'index_code'}
        if is_df:
            assert isinstance(result, PdDataFrame)
            set_keys = set(result.columns)
        else:
            logger.info(result)
            item = result[0]
            set_keys = set(item.keys())
            assert isinstance(result, list)
        assert set(set_keys) == result_keys

    @pytest.mark.parametrize('is_minimal,is_full', [(True, True), (False, False), (True, False), (False, True)])
    def test_daily_temper(self, is_minimal, is_full):
        """
        {'href': 'https://youzhiyouxing.cn/thermometer', 'date': '2022-11-24', 'temperature': 24}

        {'href': 'https://youzhiyouxing.cn/thermometer', 'date': '2022-11-24', 'temperature': 24,
     'desc': {'eval': '低估', 'trend': '温度上升'}}

        :param is_minimal:
        :param is_full:
        :return:
        """
        result = self.test_yzyx.daily_temper(is_minimal=is_minimal, is_full=is_full)
        assert result
        assert 'href' in result and 'date' in result and 'temperature' in result and isinstance(
            result.get('temperature'), int)
        if not is_minimal:
            desc = result.get('desc')
            assert desc and 'eval' in desc and 'trend' in desc
            if is_full:
                assert 'valuations' in result

# -*- coding: utf-8 -*-
"""
@Time ： 2022/11/21 18:35
@File ：test_convert.py
@IDE ：PyCharm
"""
import datetime

import pytest

from backend.fundmate.libs import convert


@pytest.mark.parametrize('date_str,expected', [('20221111', '2022-11-11'), ('2022/11/11', '2022-11-11')])
def test_try_parse_date(date_str, expected):
    result = convert.try_parse_date(date_str)
    assert str(result) == expected
    assert isinstance(result, datetime.date)

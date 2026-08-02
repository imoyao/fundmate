# -*- coding: utf-8 -*-
"""label_temp / _to_float 鲁棒性测试。

固化 2026-08-02 线上崩溃根因：集思录改版后 median_pb_temperature 等字段
以字符串形式返回（如 '22.75'），原 label_temp 直接拿字段做 ``value > 70``
比较，触发 ``'>' not supported between instances of 'str' and 'int'``。
修复后 label_temp 必须能容错字符串数值、脏值（'--'/空串/None），
不应抛出 TypeError。
"""

import pytest

from app.services.thermometer.constants import TempLevel, _to_float, label_temp


def test_to_float_plain_number():
    assert _to_float(22.75) == 22.75
    assert _to_float(10) == 10.0


def test_to_float_string_number():
    # 集思录改版后字段变为字符串，必须能解析
    assert _to_float('22.75') == 22.75
    assert _to_float('  73.56  ') == 73.56


@pytest.mark.parametrize('bad', ['--', '', 'N/A', 'NA', 'null', 'None', None])
def test_to_float_dirty_values_return_none(bad):
    assert _to_float(bad) is None


def test_label_temp_accepts_string_number_no_typeerror():
    # 核心回归：字符串数值不得抛 TypeError
    assert label_temp('22.75') == TempLevel.LOW.value
    assert label_temp('75.0') == TempLevel.HIGH.value


def test_label_temp_dirty_values_return_unknown():
    assert label_temp('--') == '未知'
    assert label_temp('') == '未知'
    assert label_temp(None) == '未知'


def test_label_temp_thresholds():
    assert label_temp(5) == TempLevel.LOW.value  # < 10
    assert label_temp(25) == TempLevel.LOW.value  # 10-40
    assert label_temp(50) == TempLevel.MID.value  # 40-70
    assert label_temp(80) == TempLevel.HIGH.value  # > 70

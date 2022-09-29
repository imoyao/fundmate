#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/1/18 17:36
@file: test_utils.py
@author: imoyao
@email: immoyao@gmail.com
@desc:
"""
import datetime
import time
from decimal import Decimal

import pendulum
import pytest

from backend.fundmate import utils


@pytest.mark.parametrize('number_of_days,expected', [(1, (0, 0, 1)), (365, (1, 0, 0)), (365, (1, 0, 0)),
                                                     (366, (1, 0, 1)), (396, (1, 1, 1))])
def test_convert_readable_days(number_of_days, expected):
    assert utils.convert_readable_days(number_of_days) == expected


def test_logger_add_ext_before_suffix():
    int_time = int(time.time())
    assert utils.logger_add_ext_before_suffix('app.log') == f'app-{int_time}.log'


@pytest.mark.parametrize('lite_dict,big_dict,expected', [
    ({
        'a': '2',
        'b': '3'
    }, {
        'a': '2',
        'b': '3',
        'c': '4'
    }, True),
    ({
        'a': '2',
        'b': '3'
    }, {
        'a': '2',
        'b': '3'
    }, True),
    ({
        'a': 2,
        'b': 3
    }, {
        'a': '2',
        'b': '3'
    }, False),
    ({
        'redeem_rule_id': 24,
        'fund_id': 103,
        'fee_type': "<FeeTypeEnum.redeem: ChoiceTypeIntegerDk(3, 'redeem', '基金赎回')>",
        'rate': Decimal('0.1'),
        'fund_code': '000134',
        'fee_amount': None
    }, {
        'id': 578,
        'fund_id': 103,
        'fund_code': '000134',
        'purchase_rule_id': None,
        'redeem_rule_id': 24,
        'fee_type': "<FeeTypeEnum.redeem: ChoiceTypeIntegerDk(3, 'redeem', '基金赎回')>",
        'rate': Decimal('0.10'),
        'fee_amount': None,
        'last_modified': datetime.datetime(2022, 3, 1, 10, 29, 54)
    }, True),
    ({
        'a': [2],
        'b': [3]
    }, {
        'a': '2',
        'b': '3'
    }, False),
])
def test_is_sub_dict(lite_dict, big_dict, expected):
    assert utils.is_sub_dict(lite_dict, big_dict) == expected


def test_today():
    td_str = utils.today()
    assert isinstance(td_str, str)
    c = utils.tomorrow(td_str)
    td = pendulum.parse(td_str).date()
    tmr = pendulum.parse(str(c)).date()
    assert (tmr - td).days == 1


def test_tomorrow():
    c = utils.tomorrow()
    tmr = pendulum.parse(str(c)).date()
    now_ = pendulum.now()
    assert (tmr - now_).days == 1


def test_seconds_today_leaves():
    sed_lev = utils.seconds_today_leaves()
    assert isinstance(sed_lev, int)
    assert sed_lev in range(0, 24 * 60 * 60 + 1)


def test_first_day_of_previous_month():
    now_date_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
    now_time = now_date_str.split()[-1]

    strict_prev_month = utils.first_day_of_previous_month(is_strict=True)
    strict_prev_month_date = pendulum.parse(strict_prev_month)
    strict_prev_mon = strict_prev_month_date.month
    strict_prev_year = strict_prev_month_date.year

    not_strict_prev_month = utils.first_day_of_previous_month(is_strict=False)
    not_strict_prev_month_date = pendulum.parse(not_strict_prev_month)
    not_strict_prev_mon = not_strict_prev_month_date.month
    not_strict_prev_year = not_strict_prev_month_date.year
    assert strict_prev_mon == not_strict_prev_mon
    assert strict_prev_year == not_strict_prev_year
    assert not_strict_prev_month.endswith('00:00:00')
    assert strict_prev_month.endswith(now_time)


@pytest.mark.parametrize('str_date,expected', [
    ('2021-01-31', datetime.date(2021, 2, 1)),
    ('2004-02-28', datetime.date(2004, 2, 29)),
    ('2005-02-28', datetime.date(2005, 3, 1)),
])
def test_tomorrow_date(str_date, expected):
    assert utils.tomorrow_date(str_date) == expected

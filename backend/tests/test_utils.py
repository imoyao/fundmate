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

import dateparser
import pendulum
import pytest

from backend.fundmate import utils


@pytest.mark.parametrize('number_of_days,expected', [(1, (0, 0, 1)), (365, (1, 0, 0)), (365, (1, 0, 0)),
                                                     (366, (1, 0, 1)), (396, (1, 1, 1))])
def test_convert_readable_days(number_of_days, expected):
    assert utils.convert_readable_days(number_of_days) == expected


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


@pytest.mark.parametrize('str_date,expected', [
    ('2021-01-31', datetime.date(2021, 2, 1)),
    ('2004-02-28', datetime.date(2004, 2, 29)),
    ('2005-02-28', datetime.date(2005, 3, 1)),
])
def test_tomorrow_date(str_date, expected):
    assert utils.tomorrow_date(str_date) == expected

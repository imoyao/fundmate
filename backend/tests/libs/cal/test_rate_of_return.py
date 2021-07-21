#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/15 11:34
from datetime import date, datetime

import pytest
from pytest import approx

from backend.fundmate import excepts
from backend.fundmate.libs.cal import rate_of_return as rr


class TestXIRRNew:

    def test_xirr(self):
        x = rr.XIRR()
        assert x.xirr([-18990, -23320, 49490],
                      [date(2016, 2, 5),
                       date(2018, 1, 26),
                       date(2018, 6, 5)]) == 0.12801613991037272


class TestXIRR:

    @pytest.mark.parametrize("values_per_date_string,expected", [
        ({
            '2019-12-31': -80005.8,
            '2020-03-12': 65209.6
        }, -0.6454),
        ({
            '2020-03-12': 65209.6,
            '2019-12-31': -80005.8
        }, -0.6454),
        ({
            '2019-12-31': -100082.76,
            '2020-03-05': 82671.24
        }, -0.6581),
        ({}, None),
        ({
            '2019-12-31': -100082.76
        }, -float("inf")),
        ({
            '2022-10-12': 200
        }, float("inf")),
        ({
            '2019-12-31': -0.00001,
            '2020-03-05': 0.00001
        }, 0.0),
        ({
            '2019-12-31': -100,
            '2020-03-05': 100
        }, 0.0),
        ({
            '2019-12-31': -100,
            '2020-03-05': 1000
        }, 412461.6383),
        ({
            '2017-12-16': -2236.3994659663,
            '2017-12-26': -47.3417585212,
            '2017-12-29': -46.52619316339632,
            '2017-12-31': 10424.74612565936,
            '2017-12-20': -13.077972551952
        }, 1.2238535289956518e+16),
        ({
            '2018-05-09': -200,
            '2018-06-09': 30,
            '2018-11-09': 50,
            '2018-12-09': 20
        }, -0.8037),
        ({
            '2011-01-01': -1,
            '2011-01-02': 0,
            '2012-01-01': -1
        }, -float("inf")),
        ({
            '2011-01-01': 1,
            '2011-01-02': 0,
            '2012-01-01': 1
        }, float("inf")),
        ({
            '2011-07-01': -10000,
            '2014-07-01': 1
        }, -0.9535),
        ({
            '2011-07-01': 10000,
            '2014-07-01': -1
        }, -0.9535),
        ({
            '2016-04-06': 18902.0,
            '2016-05-04': 83600.0,
            '2016-05-12': -5780.0,
            '2017-05-08': -4080.0,
            '2017-07-03': -56780.0,
            '2018-05-07': -2210.0,
            '2019-05-06': -2380.0,
            '2019-10-01': 33975.0,
            '2020-03-13': 23067.98,
            '2020-05-07': -1619.57,
        }, -1),
    ])
    def test_xirr(self, values_per_date_string, expected):
        values_per_date = {
            datetime.fromisoformat(k).date(): v
            for k, v in values_per_date_string.items()
        }
        _val_list = list(values_per_date.values())
        _dates = list(values_per_date.keys())
        actual = rr.xirr.xirr(_val_list, _dates)
        if expected and actual is not None:
            assert round(actual, 4) == expected
        else:
            assert actual == expected

    @pytest.mark.parametrize("values_per_date_string,expected", [
        ({
            '2019-12-31': -80005.8,
            '2020-03-12': 65209.6
        }, -0.6454),
        ({
            '2020-03-12': 65209.6,
            '2019-12-31': -80005.8
        }, -0.6454),
        ({
            '2019-12-31': -100082.76,
            '2020-03-05': 82671.24
        }, -0.6581),
        ({}, None),
        ({
            '2019-12-31': -0.00001,
            '2020-03-05': 0.00001
        }, None),
        ({
            '2019-12-31': -100,
            '2020-03-05': 100
        }, None),
        ({
            '2019-12-31': -100,
            '2020-03-05': 1000
        }, None),
        ({
            '2018-05-09': -200,
            '2018-06-09': 30,
            '2018-11-09': 50,
            '2018-12-09': 20
        }, -0.8037),
        ({
            '2011-01-01': 1,
            '2011-01-02': 0,
            '2012-01-01': 1
        }, None),
        ({
            '2011-01-01': -559.50,
            '2011-01-02': 4650.96
        }, None),
    ])
    def test_clean_xirr(self, values_per_date_string, expected):
        values_per_date = {
            datetime.fromisoformat(k).date(): v
            for k, v in values_per_date_string.items()
        }
        print(values_per_date, 'values_per_date-----')
        # return None
        _val_list = list(values_per_date.values())
        _dates = list(values_per_date.keys())
        actual = rr.xirr.clean_xirr(_val_list, _dates)
        if expected and actual is not None:
            assert round(actual, 4) == expected
        else:
            assert actual == expected


class TestXNPV:

    @pytest.mark.parametrize("values_per_date_string,rate,expected", [
        ({
            '2019-12-31': -100,
            '2020-12-31': 110
        }, -1.0, float('inf')),
        ({
            '2019-12-31': -100,
            '2020-12-31': 110
        }, -0.10, 22.2575),
    ])
    def test_xnpv(self, values_per_date_string, rate, expected):
        values_per_date = {
            datetime.fromisoformat(k).date(): v
            for k, v in values_per_date_string.items()
        }
        actual = rr.xnpv.xnpv(values_per_date, rate)
        if expected:
            assert actual == approx(expected, 0.0001)
        else:
            assert actual == expected

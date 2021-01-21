#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Administrator at 2021/1/21 23:10
"""
[XIRR 函数 - Office 支持](https://support.microsoft.com/zh-cn/office/xirr-%E5%87%BD%E6%95%B0-de1242ec-6477-445b-b11b-a303ad9adc9d)

https://github.com/tarioch/xirr
based on https://stackoverflow.com/questions/8919718/financial-python-library-that-has-xirr-and-xnpv-function
with some handling for special cases from
https://github.com/RayDeCampo/java-xirr/blob/master/src/main/java/org/decampo/xirr/Xirr.java
"""
import scipy.optimize
import dateparser

DAYS_PER_YEAR = 365.0


def try_parsing_date(text):
    """
    try and parse date
    :param text: string
    :return: date part of datetime object
    """
    try:
        return dateparser.parse(text).date()
    except:
        pass


def xnpv(valuesPerDate, rate):
    """Calculate the irregular net present value.

    >>> from datetime import date
    >>> valuesPerDate = {date(2019, 12, 31): -100, date(2020, 12, 31): 110}
    >>> xnpv(valuesPerDate, -0.10)
    22.257507852701295
    """

    if rate == -1.0:
        return float('inf')

    t0 = min(valuesPerDate.keys())

    if rate <= -1.0:
        return sum([-abs(vi) / (-1.0 - rate) ** ((ti - t0).days / DAYS_PER_YEAR) for ti, vi in valuesPerDate.items()])

    return sum([vi / (1.0 + rate) ** ((ti - t0).days / DAYS_PER_YEAR) for ti, vi in valuesPerDate.items()])


def xirr(valuesPerDate):
    """Calculate the irregular internal rate of return.

    >>> from datetime import date
    >>> valuesPerDate = {date(2019, 12, 31): -80005.8, date(2020, 3, 12): 65209.6}
    >>> xirr(valuesPerDate)
    -0.645363882724717
    """
    if not valuesPerDate:
        return None

    if all(v >= 0 for v in valuesPerDate.values()):
        return float("inf")
    if all(v <= 0 for v in valuesPerDate.values()):
        return -float("inf")

    try:
        result = scipy.optimize.newton(lambda r: xnpv(valuesPerDate, r), 0)
    except (RuntimeError, OverflowError):  # Failed to converge?
        result = scipy.optimize.brentq(lambda r: xnpv(valuesPerDate, r), -0.999999999999999, 1e20, maxiter=10 ** 6)

    if not isinstance(result, complex):
        return result
    else:
        return None


def cleanXirr(valuesPerDate):
    """A "cleaned" version of the xirr which avoids returning a xirr for some extreme cases and ignores amounts which are almost 0.
    """
    valuesPerDateCleaned = {}
    for date, amount in valuesPerDate.items():
        if round(amount, 2) != 0:
            valuesPerDateCleaned[date] = amount
    try:
        result = xirr(valuesPerDateCleaned)
    except ValueError:
        return None
    if result is not None and (abs(result) >= 100 or round(result, 4) == 0):
        return None
    else:
        return result


def xirr_df(df, date='date', amount='amount'):
    """
    see also: [Pass Pandas DataFrame as input · Issue #16 · tarioch/xirr](https://github.com/tarioch/xirr/issues/16)
    :param df: pandas df
    :param date: date column name
    :param amount: amount column name
    :return: xirr for given date and amount values
    """

    dates = df[date].tolist()
    amounts = df[amount].tolist()
    dates_parsed = list(map(try_parsing_date, dates))
    valuesPerDate = dict(zip(dates_parsed, amounts))
    return xirr(valuesPerDate)

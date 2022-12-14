#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/11 0:27
"""
一些数据转换的工具模块
"""
import locale
import warnings
from distutils import util
from typing import Optional, Union

import dateparser
import pendulum

from backend.fundmate import excepts


# ref: https://github.com/scrapinghub/dateparser/issues/1013
warnings.filterwarnings(
    "ignore",
    message="The localize method is no longer necessary, as this time zone supports the fold attribute",
)


def percent2float(x: str) -> float:
    """
    >>> y = '20%'
    >>> percent2float(y)
    0.2

    :param x:
    :return:
    """
    return float(x.strip('%')) / 100


def word_for_true(word: str) -> bool:
    """
    转换为Bool
    :param word:
    :return:
    """
    return bool(util.strtobool(word))


def try_parse_date(text: str, **opts):
    """
    尝试将一个字符串解析为date类型
    >>> try_parse_date('20221111')
    Date(2022, 11, 11)
    >>> try_parse_date('2022/11/11')
    Date(2022, 11, 11)
    >>> try_parse_date('2022年11月22日 20:00')
    datetime.date(2022, 11, 22)
    >>> try_parse_date('2022/11/29 10:00:00')
    Date(2022, 11, 29)

    :param text: string
    :return: date part of datetime object
    """
    try:
        parse_ret = pendulum.parse(text, **opts)
    except (Exception,):
        parse_ret = dateparser.parse(text)
    if parse_ret:
        return parse_ret.date()
    else:
        raise excepts.ParseError(f'Can not parse {text},please check whether is a date like str?')


def try_parse_number(text: str) -> Union[int, float]:
    """
    parse string to int/float
    >>> try_parse_number('2000.12')
    2000.12

    >>> try_parse_number('200,012')
    200012

    >>> try_parse_number('200,012.12')
    200012.12

    >>> try_parse_number('20,012.12')
    20012.12

    :param text:
    :return:
    """
    if ',' in text:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        if '.' in text:
            val = locale.atof(text)
        else:
            val = locale.atoi(text)
    else:
        if '.' in text:
            val = float(text)
        else:
            val = int(text)
    return val


def to_percent(rate_val: Optional[float]) -> str:
    """
    返回费率需要加百分号
    >>> x = 1.2
    >>> to_percent(x)
    '1.20%'
    >>> x = None
    >>> to_percent(x)
    '0.00%'

    :param rate_val:
    :return:
    """
    if rate_val is None:
        rate_val = 0
    return f'{rate_val:.2f}%'


def none_to_inf(rate_value: Optional[float]) -> float:
    """
    >>> x = None
    >>> none_to_inf(x)
    inf
    """
    if rate_value is None:
        return float('inf')
    return float(rate_value)


def with_thousands_separator(quota) -> Union[str, float]:
    """
    为了更好阅读性，增加千位分隔符

    >>> x = 100000000000
    >>> with_thousands_separator(x)
    '100,000,000,000.0'

    :param quota:
    :return:
    """
    math_quota = none_to_inf(quota)
    if math_quota is not float('inf'):
        return f'{math_quota:,}'
    return math_quota

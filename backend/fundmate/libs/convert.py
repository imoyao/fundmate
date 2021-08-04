#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/11 0:27
import locale
from distutils import util
from typing import Union

import dateparser

from backend.fundmate import excepts


def percent2float(x: str) -> float:
    return float(x.strip('%')) / 100


def word_for_true(word: str) -> bool:
    """
    装换为Bool
    :param word:
    :return:
    """
    return util.strtobool(word)


def try_parse_date(text: str):
    """
    尝试将一个字符串解析为date类型
    try and parse date
    :param text: string
    :return: date part of datetime object
    """
    parse_ret = dateparser.parse(text)
    if parse_ret:
        return parse_ret.date()
    else:
        raise excepts.ParseError(f'Can not parse {text},please check whether is a date like str?')


def try_parse_number(text: str) -> Union[int, float]:
    """
    parse string to int/float
    >>> try_parse_number('2000.12')
    >>> 2000.12

    >>> try_parse_number('200,012')
    >>> 200012

    >>> try_parse_number('200,012.12')
    >>> 200012.12

    >>> try_parse_number('20,012.12')
    >>> 20012.12
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

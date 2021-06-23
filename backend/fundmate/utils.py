# -*- coding: utf-8 -*-
"""Helper utilities and decorators.
整个项目中的工具函数
TODO: 如果后期变大，则拆分为多个文件
"""
from datetime import datetime, timedelta

import dateparser


def today() -> str:
    """
    a = datetime.today()
    datetime.datetime(2021, 6, 7, 17, 27, 13, 713125)
    a.strftime("%Y-%m-%d")
    '2021-06-07'
    :return:
    """
    return datetime.today().strftime("%Y-%m-%d")


def first_day_of_this_year() -> str:
    return datetime.today().replace(month=1, day=1).strftime("%Y-%m-%d")


def first_day_of_this_month() -> str:
    return dateparser.parse(str(datetime.today().month), settings={'PREFER_DAY_OF_MONTH': 'first'}).strftime("%Y-%m-%d")


def seconds_today_leaves() -> int:
    tomorrow = datetime.strptime(today(), "%Y-%m-%d") + timedelta(days=1)
    return (tomorrow - datetime.now()).seconds


if __name__ == '__main__':
    print(first_day_of_this_year(), first_day_of_this_month(),seconds_today_leaves())

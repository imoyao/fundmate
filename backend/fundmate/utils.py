# -*- coding: utf-8 -*-
"""Helper utilities and decorators.
整个项目中的工具函数
TODO: 如果后期变大，则拆分为多个文件
"""
import itertools
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Union

import dateparser


def show_time(func):
    """
    代码耗时时间计算
    """

    def wrap_func(*args, **kwargs):
        start_time = time.time()
        ret_result = func(*args, **kwargs)
        end_time = time.time()
        print('The function **{0}** takes {1} time.'.format(
            func.__name__, end_time - start_time))
        return ret_result

    return wrap_func


def merge_iterables_of_dict(shared_key, *iterables):
    """
    内字典列表合并
    :param shared_key:
    :param iterables:
    :return:
    """
    result = defaultdict(dict)
    for dictionary in itertools.chain.from_iterable(iterables):
        result[dictionary[shared_key]].update(dictionary)
    for dictionary in result.values():
        dictionary.pop(shared_key)
    return result


class HiddenPrints:
    """
    禁止调用函数中的打印信息
    """

    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout


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
    return dateparser.parse(str(datetime.today().month),
                            settings={
                                'PREFER_DAY_OF_MONTH': 'first'
                            }).strftime("%Y-%m-%d")


def seconds_today_leaves() -> int:
    tmr = tomorrow()
    return (tmr - datetime.now()).seconds


def tomorrow(str_date: Union[str, None] = None):
    if not str_date:
        str_date = str(datetime.strptime(today(), "%Y-%m-%d").date())
    if not isinstance(str_date, str):
        str_date = str(str_date)
    date = dateparser.parse(str_date)
    return date + timedelta(days=1)


def tomorrow_date(str_date: Union[str, None] = None) -> datetime.date:
    """
    Examples:
    ```
    # today is 2021-06-24
    tomorrow_date()
    2021-06-25
    tomorrow_date('2021-06-30')
    2021-07-01
    ```
    :param str_date: 
    :return: 
    """
    return tomorrow(str_date).date()


if __name__ == '__main__':
    print(first_day_of_this_year(), first_day_of_this_month(),
          seconds_today_leaves(), tomorrow_date('2021-06-30'))

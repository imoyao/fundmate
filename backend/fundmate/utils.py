# -*- coding: utf-8 -*-
"""Helper utilities and decorators.
整个项目中的工具函数
"""
import itertools
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path, PurePath
from typing import Dict, List, Optional, Union

import dateparser
import pendulum

from backend.fundmate.exts.flask_loguru import logger


def logger_add_ext_before_suffix(logger_file_name: str):
    """
    日志文件添加时间戳
    """
    file_stem = PurePath(logger_file_name).stem
    file_suffix = PurePath(logger_file_name).suffix
    return f'{file_stem}-{int(time.time())}{file_suffix}'


def convert_readable_days(number_of_days: int) -> tuple:
    """
    天数转换为年月日（不考虑闰年）
    """
    years = number_of_days // 365
    # Calculating months
    months = (number_of_days - years * 365) // 30
    # Calculating days
    days = number_of_days - years * 365 - months * 30
    return years, months, days


def is_sub_dict(subset_dict: dict, superset_dict: dict):
    """
    测试前字典是否为后字典的子集
    FIXME: PY3.9:  return big | small == big

    >>> d1 = {'a':'2', 'b':'3'}
    >>> d2 = {'a':'2', 'b':'3','c':'4'}
    >>> is_sub_dict(d1,d2)
    True

    >>> d1 = {'a':'2', 'b':'3'}
    >>> d2 = {'a':'2', 'b':'3'}
    >>> is_sub_dict(d1,d2)
    True

    >>> d1 = {'a':1, 'b':4}
    >>> d2 = {'a':'2', 'b':'3'}
    >>> is_sub_dict(d1,d2)
    False

    :param subset_dict:
    :param superset_dict:
    :return:
    """
    return all(item in superset_dict.items() for item in subset_dict.items())


def show_time(func):
    """
    代码耗时时间计算
    """

    def wrap_func(*args, **kwargs):
        start_time = time.time()
        ret_result = func(*args, **kwargs)
        end_time = time.time()
        print('The function **{0}** takes {1} time.'.format(func.__name__, end_time - start_time))
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


def key2val(unique_dict: dict) -> dict:
    return {v: k for k, v in unique_dict.items()}


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
    return str(datetime.today().date())


def first_day_of_this_year() -> str:
    return datetime.today().replace(month=1, day=1).strftime('%Y-%m-%d')


def first_day_of_this_month() -> str:
    now = pendulum.parse('now')
    return str(now.replace(day=1).date())


def first_day_of_previous_month(is_strict: bool = True) -> str:
    """
    :param is_strict:True: 严格一个月之前 今天的时分秒 False: 一个月之前的一号 00：00：00
    :return:
    """
    now = pendulum.parse('now')
    previous_month = now.subtract(months=1)
    if not is_strict:
        previous_month = previous_month.replace(day=1, hour=0, minute=0, second=0)
    return previous_month.to_datetime_string()


def seconds_today_leaves() -> int:
    tmr = tomorrow()
    _now = pendulum.now()
    delta = tmr - _now
    return delta.seconds


def tomorrow(str_date: Optional[str] = None) -> datetime.date:
    if not str_date:
        str_date = pendulum.tomorrow()
        return str_date
    if not isinstance(str_date, str):
        str_date = str(str_date)
    date = dateparser.parse(str_date)
    return date + timedelta(days=1)


def tomorrow_date(str_date: Optional[str] = None) -> datetime.date:
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


def write_json_data(data: Union[str, List, Dict], fp: Union[str, Path], indent: int = 2):
    """
    写json文件
    :param data:
    :param fp:
    :param indent:
    :return:
    """
    fp = Path(fp)
    dir_name = fp.parent
    if not dir_name.exists():
        dir_name.mkdir(parents=True)
        msg = f'目录:{str(fp)} 新建成功以保存数据。'
        logger.info(msg)
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


def cal_durations(previous_date: datetime, next_date: datetime) -> int:
    """
    基金持有时长(比如持有7天)便是按自然日来计算的
    :param previous_date: 较小的日期
    :param next_date: 较大的日期
    :return:
    """
    return (next_date - previous_date).days


def check_is_csv(fp: Union[str, Path]) -> Optional[bool]:
    """
    判断文件存在并确定格式正确
    :param fp:
    :return:
    """
    path = Path(fp)
    if path.exists() and path.is_file():
        file_suffix = path.suffix
        return file_suffix.lower() == 'csv'


if __name__ == '__main__':
    print(first_day_of_this_year(), first_day_of_this_month(), seconds_today_leaves(), tomorrow(),
          tomorrow_date('2021-06-30'), tomorrow_date())

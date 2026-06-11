# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 21:47
# File : utils.py
# app/core/utils.py

"""通用工具函数，如分页等。"""

import datetime
import json
import os
import sys
import time
from datetime import date
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pendulum
from chinese_calendar import find_workday
from flask import jsonify
from loguru import logger
from sqlalchemy.orm import Query

from app.core.database import get_db


def api_response(data=None, message='ok', total=None):
    """统一 JSON 响应格式."""
    resp = {'data': data, 'message': message}
    if total is not None:
        resp['total'] = total
    return jsonify(resp)


def with_db(func):
    """装饰器：自动注入数据库会话并返回统一格式."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        with get_db() as db:
            return func(db, *args, **kwargs)

    return wrapper


def paginate(query: Query, page: int = 1, per_page: int = 20) -> Tuple[List[Any], int]:
    """
    对查询进行分页，返回 (items, total)。
    page 从 1 开始，per_page 默认 20。
    """
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, total


def get_confirm_date(purchase_date: date, fund_type: str = 'domestic', is_after_15: bool = False) -> date:
    """
    计算场外基金确认日。

    Args:
        purchase_date: 购买日（T日）
        fund_type: 基金类型，'domestic'（普通场外基金）或 'qdii'（QDII基金）
        is_after_15: 是否在15:00之后下单，若为True则T日顺延一个工作日

    Returns:
        确认日（净值确认日期）
    """
    # 如果15:00之后下单，T日顺延一个工作日
    if is_after_15:
        purchase_date = find_workday(delta_days=1, date=purchase_date)

    # QDII基金 T+2，普通基金 T+1
    delta_days = 2 if fund_type == 'qdii' else 1

    return find_workday(delta_days=delta_days, date=purchase_date)


def rename_with_extra_suffix(file_name: str, extra_suffix: Optional[str] = None) -> str:
    """给文件名添加后缀（在扩展名前）。"""
    if not extra_suffix:
        extra_suffix = str(int(time.time()))
    stem = Path(file_name).stem
    suffix = Path(file_name).suffix
    return f'{stem}-{extra_suffix}{suffix}'


def convert_readable_days(number_of_days: int) -> tuple:
    """天数转换为年月日（不考虑闰年）。"""
    years = number_of_days // 365
    months = (number_of_days - years * 365) // 30
    days = number_of_days - years * 365 - months * 30
    return years, months, days


def is_sub_dict(subset_dict: dict, superset_dict: dict) -> bool:
    """判断 subset_dict 是否为 superset_dict 的子集。"""
    return all(item in superset_dict.items() for item in subset_dict.items())


def show_time(func):
    """装饰器：打印函数执行耗时。"""

    def wrap_func(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        print(f'函数 {func.__name__} 耗时 {end_time - start_time:.4f} 秒')
        return result

    return wrap_func


def key2val(unique_dict: dict) -> dict:
    """字典键值互换（值必须可哈希）。"""
    return {v: k for k, v in unique_dict.items()}


class HiddenPrints:
    """上下文管理器：临时禁止 print 输出。"""

    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout


def first_day_of_this_year() -> str:
    """返回本年第一天的日期字符串（YYYY-MM-DD）。"""
    return pendulum.now().start_of('year').to_date_string()


def first_day_of_this_month() -> str:
    """返回本月第一天的日期字符串（YYYY-MM-DD）。"""
    return pendulum.now().start_of('month').to_date_string()


def first_day_of_previous_n_months(is_strict: bool = True, months: int = 1) -> str:
    """
    返回 N 个月前的第一天。

    Args:
        is_strict: True 表示严格 N 个月前（保留时分秒），False 表示 N 个月前第一天的 00:00:00
        months: 月数

    Returns:
        ISO 格式字符串（如 '2025-01-01 00:00:00'）
    """
    now = pendulum.now()
    prev = now.subtract(months=months)
    if not is_strict:
        prev = prev.start_of('month')
    return prev.to_datetime_string()


def seconds_today_leaves() -> int:
    """返回今日剩余秒数。"""
    tomorrow = pendulum.tomorrow().start_of('day')
    now = pendulum.now()
    delta = tomorrow - now
    return delta.seconds


def tomorrow(date_str: Optional[str] = None):
    """
    返回明天的 datetime 对象。
    如果提供 date_str，则返回该日期下一天的 datetime。
    """
    if date_str is None:
        return pendulum.tomorrow()
    dt = pendulum.parse(date_str)
    return dt.add(days=1)


def tomorrow_date(date_str: Optional[str] = None) -> str:
    """返回明天的日期字符串（YYYY-MM-DD）。"""
    dt = tomorrow(date_str)
    return dt.to_date_string()


def write_json_data(data: Union[str, List, Dict], fp: Union[str, Path], indent: int = 2):
    """将数据写入 JSON 文件（自动创建父目录）。"""
    path = Path(fp)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    logger.info(f'JSON 数据已写入: {path}')


def cal_durations(previous_date, next_date) -> int:
    """
    计算两个日期之间的自然日差值。
    参数可以是 datetime 或 date 对象，或可解析的字符串。
    """
    if isinstance(previous_date, str):
        previous_date = pendulum.parse(previous_date)
    if isinstance(next_date, str):
        next_date = pendulum.parse(next_date)
    return (next_date - previous_date).days


def check_is_csv(fp: Union[str, Path]) -> bool:
    """判断文件是否存在且后缀为 .csv（不区分大小写）。"""
    path = Path(fp)
    return path.exists() and path.is_file() and path.suffix.lower() == '.csv'


def to_camelcase(var: str) -> str:
    """转换为小驼峰命名（lowerCamelCase）。"""
    # 将下划线/横线分隔的单词转为驼峰
    import re

    pattern = re.compile(r'[_-]+')
    var = pattern.sub(' ', var).title().replace(' ', '')
    return var[0].lower() + var[1:] if var else var


def to_snakecase(var: str) -> str:
    """转换为蛇形命名（snake_case）。"""
    import re

    pattern = re.compile(r'(?<!^)(?=[A-Z])')
    return pattern.sub('_', var).lower()


if __name__ == '__main__':
    date = get_confirm_date(datetime.date(2026, 5, 1))
    print(date)

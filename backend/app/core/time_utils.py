# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 17:05
# File : time_utils.py
# -*- coding: utf-8 -*-
"""统一的时间工具，所有时间相关操作必须从此模块获取当前时间"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo('Asia/Shanghai')


def now_shanghai() -> datetime:
    """返回当前上海时区的 datetime 对象"""
    return datetime.now(SHANGHAI_TZ)


def today_shanghai() -> date:
    """返回当前上海时区的 date 对象"""
    return now_shanghai().date()

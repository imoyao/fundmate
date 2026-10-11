# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 17:05
# File : time_utils.py
# -*- coding: utf-8 -*-
"""统一的时间工具，所有时间相关操作必须从此模块获取当前时间"""

from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo('Asia/Shanghai')


def now_shanghai() -> datetime:
    """返回当前上海时区的 datetime 对象"""
    return datetime.now(SHANGHAI_TZ)


def as_shanghai(dt: Optional[datetime]) -> Optional[datetime]:
    """把 datetime 归一为**东八区 aware**，用于跨来源的时间比较（#1793）。

    为什么需要：SQLite 的 DateTime 列不保留时区偏移——写入时是 aware（如
    `job.snapshot_time = now_shanghai()`），读回来却是 naive 的东八区墙钟时间。
    两侧直接相减会抛 `TypeError: can't subtract offset-naive and offset-aware
    datetimes`，且该错误只在「读 DB 的值再与 now_shanghai() 比较」时出现，
    典型的隐藏缺陷（health 端点的调度健康判定即因此 500）。

    口径（务必与本项目既有约定一致，勿改成 UTC 假设）：
    - naive：按**东八区墙钟时间**补齐 tzinfo；
    - aware：统一 `astimezone` 到 Asia/Shanghai；
    - None：原样返回，便于调用方链式判空。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=SHANGHAI_TZ)
    return dt.astimezone(SHANGHAI_TZ)


def today_shanghai() -> date:
    """返回当前上海时区的 date 对象"""
    return now_shanghai().date()

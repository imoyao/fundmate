# -*- coding: utf-8 -*-
"""定时任务随机化（jitter）——抓取礼仪（#1400）。

背景：外部 cron（GitHub Actions / SCF / 系统 cron）只能触发**固定时刻**（如每天
00:00），对数据源而言就是「每天同一秒准时来一次」的机器人指纹。成熟爬虫的通行做法
是在**任务入口**加随机起跑延迟（jitter），把触发时刻摊平到一个时间窗内。

为何不用 APScheduler：`CronTrigger(jitter=...)` 是标准解法，但本项目**不引入常驻
调度器**（见 app/tools/scheduler.py 顶部注释：由外部定时器触发），故用更轻的实现——
入口 sleep 一段均匀随机时长，零依赖、对任何外部触发器都生效。

用法：
    from app.core.jitter import resolve_jitter_seconds, apply_jitter, random_gap

    apply_jitter(resolve_jitter_seconds(args.jitter), label='每日同步')
    ...每个 job 之间...
    random_gap(label='job 间隔')
"""

import os
import random
import time
from typing import Optional

from loguru import logger

# 默认抖动窗口：10 分钟——足以打散「每天同一时刻」的指纹，又不会让任务漂得太晚
DEFAULT_JITTER_SECONDS = 600
# 任务之间的随机间隔上限（秒）：避免短时间连打同一个数据源
DEFAULT_JOB_GAP_SECONDS = 5

ENV_JITTER_SECONDS = 'SYNC_JITTER_SECONDS'
ENV_JOB_GAP_SECONDS = 'SYNC_JOB_GAP_SECONDS'


def resolve_jitter_seconds(cli_value: Optional[int] = None) -> int:
    """解析抖动窗口（秒）。优先级：命令行 > 环境变量 > 默认；0/负数表示不抖动。"""
    if cli_value is not None:
        return max(0, int(cli_value))
    raw = os.getenv(ENV_JITTER_SECONDS)
    if raw:
        try:
            return max(0, int(float(raw)))
        except (TypeError, ValueError):
            logger.warning(f'{ENV_JITTER_SECONDS}={raw!r} 无法解析，回退默认 {DEFAULT_JITTER_SECONDS}s')
    return DEFAULT_JITTER_SECONDS


def resolve_job_gap_seconds(cli_value: Optional[int] = None) -> int:
    """解析任务间隔上限（秒）；语义同上。"""
    if cli_value is not None:
        return max(0, int(cli_value))
    raw = os.getenv(ENV_JOB_GAP_SECONDS)
    if raw:
        try:
            return max(0, int(float(raw)))
        except (TypeError, ValueError):
            logger.warning(f'{ENV_JOB_GAP_SECONDS}={raw!r} 无法解析，回退默认 {DEFAULT_JOB_GAP_SECONDS}s')
    return DEFAULT_JOB_GAP_SECONDS


def apply_jitter(window_seconds: int, label: str = '调度') -> int:
    """随机延迟 uniform(0, window) 秒后返回实际延迟；window<=0 不延迟。"""
    if window_seconds <= 0:
        logger.info(f'{label}：未启用 jitter（窗口 0s）')
        return 0
    delay = random.uniform(0, window_seconds)
    logger.info(f'{label}：jitter 随机延迟 {delay:.1f}s（窗口 {window_seconds}s）')
    time.sleep(delay)
    return int(delay)


def random_gap(
    min_seconds: int = 1,
    max_seconds: int = DEFAULT_JOB_GAP_SECONDS,
    label: str = '',
) -> float:
    """任务间随机间隔：避免对同一/相邻数据源形成突发请求。max<=0 则跳过。"""
    if max_seconds <= 0:
        return 0.0
    low = max(0, min_seconds)
    high = max(low, max_seconds)
    gap = random.uniform(low, high)
    if label:
        logger.debug(f'{label}：任务间隔 {gap:.1f}s')
    time.sleep(gap)
    return gap

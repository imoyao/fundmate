# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/8 21:08
# File : __init__.py.py

import logging

from loguru import logger

# 全局请求补丁：进程启动时让所有 akshare/requests 调用自动走「浏览器头 + 连接复用 + 重试」会话，
# 缓解东方财富按 IP 限流/临时封导致的 RemoteDisconnected（详见 app/core/requests_patch.py；根因仍待退出代理后 diag 验收）。
from app.core.requests_patch import install_requests_patch

install_requests_patch()

# 防御性限速：降低单 IP 请求频率，缓解东财按 IP 限流/临时封。
# request_interval=3 表示相邻请求至少间隔 3 秒；use_thread=False 避免并发连接触发风控。
try:
    import akshare as ak

    ak.set_option('request_interval', 3)
    ak.set_option('use_thread', False)
except Exception:  # pragma: no cover - 仅在缺 akshare 时跳过，不影响启动
    pass


class InterceptHandler(logging.Handler):
    """将标准库 logging 日志转发到 loguru"""

    def emit(self, record: logging.LogRecord) -> None:
        # 获取 loguru 对应的日志级别，如果找不到则直接使用数字级别
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        # 将异常信息、调用栈等附加信息一并传递
        logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())

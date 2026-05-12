# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/12 20:58
# File : request_engine.py
import random
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import requests
from fake_useragent import UserAgent
from loguru import logger


class SmartRequestController:
    """智能请求控制器：动态UA + 自适应延迟 + 会话保持 + 自动重试"""

    def __init__(self, max_retries=3):
        self.ua = UserAgent()
        self.request_timestamps = []
        self.max_retries = max_retries
        self.session = self._create_new_session()

    def _create_new_session(self) -> requests.Session:
        """创建新的会话对象，设置随机User-Agent和基础头信息"""
        session = requests.Session()
        session.headers = {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        return session

    def _calculate_sleep_time(self) -> float:
        """智能计算请求间隔时间，模拟人类行为"""
        base_sleep = random.uniform(3, 5)
        if len(self.request_timestamps) >= 10:
            recent_requests = self.request_timestamps[-10:]
            avg_interval = (recent_requests[-1] - recent_requests[0]).total_seconds() / 9
            if avg_interval < 3:
                base_sleep = random.uniform(8, 12)
        now = datetime.now()
        if (9 <= now.hour < 11.5) or (13 <= now.hour < 15):
            base_sleep *= 1.2
        return base_sleep

    def fetch(self, fn, *args, **kwargs) -> Optional[pd.DataFrame]:
        """带智能反爬控制的请求方法"""
        for attempt in range(self.max_retries):
            try:
                sleep_time = self._calculate_sleep_time()
                time.sleep(sleep_time)
                result = fn(*args, **kwargs)
                self.request_timestamps.append(datetime.now())
                if len(self.request_timestamps) > 100:
                    self.request_timestamps.pop(0)
                return result
            except Exception as e:
                logger.warning(f'请求失败 (尝试 {attempt + 1}/{self.max_retries}): {e}')
                if attempt == self.max_retries - 1:
                    raise
                self.session = self._create_new_session()
                time.sleep(random.uniform(10, 15))
        return None


# 全局单例
_controller: Optional[SmartRequestController] = None


def get_request_controller() -> SmartRequestController:
    global _controller
    if _controller is None:
        _controller = SmartRequestController()
    return _controller

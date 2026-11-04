# -*- coding: utf-8 -*-
"""进程内固定窗口限流（零依赖）。

用途：`POST /api/auth/resolve/` 这类**匿名**端点。它把「用户名 → 邮箱」暴露给任何
不带凭证的调用方，不限流等于提供一条批量枚举通道（#2764 遗留项）。

**能力边界要写清楚，别把它当成配额系统**：状态在进程内存，多 worker（gunicorn 多
进程 / 多容器）下各自计数，实际阈值是「单进程阈值 × 进程数」。这是**有意的取舍**——
为单个端点引入 Redis 不划算，而「单进程 20 次/分钟」已经能把脚本枚举从「几万次/分钟」
压到「需要几千个 IP 才划算」。要严格配额时换后端实现即可，调用方签名不变。

与 `app/services/ai_recognizer/guards.py::_check_rate_limit` 的关系：那边是**按用户**
的配额（已登录、按天/按分钟计费语义），这里按**来源**（IP）计。两者语义不同，不合并。
"""

import threading
import time
from typing import Dict, Tuple

_LOCK = threading.Lock()
#: key = (桶键, 窗口序号)，value = 窗口内已计数
_BUCKETS: Dict[Tuple[str, int], int] = {}


def check(key: str, *, limit: int, window_seconds: int = 60) -> bool:
    """记一次调用并判断是否放行（True = 放行，False = 超限）。

    固定窗口（不是滑动窗口）：窗口边界处允许短时 2 倍突发。对「防枚举」这个目的
    足够——攻击者拿不到「边界在哪」的信息，而实现简单到可以一眼看穿。

    每次调用顺带清理过期桶，避免字典随不同 key（IP）无限膨胀。
    """
    if limit <= 0:
        return True
    now = int(time.time())
    bucket_key = (key, now // window_seconds)
    with _LOCK:
        cutoff = now - window_seconds * 2
        for k in [k for k in _BUCKETS if k[1] * window_seconds < cutoff]:
            _BUCKETS.pop(k, None)
        count = _BUCKETS.get(bucket_key, 0)
        if count >= limit:
            return False
        _BUCKETS[bucket_key] = count + 1
        return True


def reset_all() -> None:
    """清空全部计数（测试用：避免用例之间互相消耗配额导致 flaky）。"""
    with _LOCK:
        _BUCKETS.clear()

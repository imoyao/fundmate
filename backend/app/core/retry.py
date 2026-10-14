# -*- coding: utf-8 -*-
"""请求级「database is locked」重试装饰器.

背景：dev 单库模式下 web 请求与进程内 scheduler 共用同一 SQLite 文件（WAL）。
删除类端点先 SELECT 建立读快照，若期间 scheduler 提交了写事务，随后的 DELETE
尝试把**过期读快照**升级为写锁，SQLite 会立即返回 SQLITE_BUSY——busy_timeout
对「读快照升级写锁」不生效——表现为 ``database is locked``。

正确恢复方式：回滚当前请求会话（放弃过期快照）、短暂等待后**重跑整个视图逻辑**
（重新拿快照、重新校验、重新执行删除）。原地重试单条 DELETE 无效：快照仍过期。

仅装饰幂等的删除类端点；非 locked 的 OperationalError 一律原样抛出。
"""

import random
import time
from functools import wraps

from sqlalchemy import exc as sa_exc

from app.core.database import rollback_request_sessions

_LOCKED_MARK = 'database is locked'


def retry_on_db_locked(max_attempts: int = 3, base_delay: float = 0.2):
    """捕获 ``database is locked`` 后回滚请求会话并重试整个被装饰函数。

    - 只对消息含 ``database is locked`` 的 ``OperationalError`` 重试；
    - 重试前调用 :func:`rollback_request_sessions` 放弃过期 WAL 读快照
      （原因见模块 docstring，不回滚则重跑仍在旧快照上失败）；
    - 间隔 ``base_delay * 2**attempt`` + 随机 jitter，避免与写持有者硬碰；
    - 达到 ``max_attempts`` 仍 locked 时抛出最后一次异常。
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except sa_exc.OperationalError as err:
                    if _LOCKED_MARK not in str(err) or attempt >= max_attempts - 1:
                        raise
                    rollback_request_sessions()
                    time.sleep(base_delay * (2**attempt) + random.uniform(0, 0.1))
            raise RuntimeError('unreachable: loop always returns or raises')  # pragma: no cover

        return wrapper

    return decorator

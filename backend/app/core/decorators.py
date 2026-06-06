# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/3 23:17
# File : decorators.py
"""通用装饰器"""

import warnings
from functools import wraps


def deprecated(message: str = ''):
    """标记函数或类为废弃，调用时产生 DeprecationWarning 警告"""

    def decorator(obj):
        if isinstance(obj, type):
            # 对于类，装饰其 __init__ 方法
            original_init = obj.__init__

            @wraps(original_init)
            def new_init(self, *args, **kwargs):
                warnings.warn(
                    f'{obj.__name__} 已被废弃，将在未来版本中移除。{message}', DeprecationWarning, stacklevel=2
                )
                original_init(self, *args, **kwargs)

            obj.__init__ = new_init
            return obj
        else:
            # 对于函数
            @wraps(obj)
            def wrapper(*args, **kwargs):
                warnings.warn(
                    f'{obj.__name__} 已被废弃，将在未来版本中移除。{message}', DeprecationWarning, stacklevel=2
                )
                return obj(*args, **kwargs)

            return wrapper

    return decorator

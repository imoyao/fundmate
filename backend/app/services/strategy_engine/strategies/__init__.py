# -*- coding: utf-8 -*-
"""策略实现注册入口。

新增一个策略 = ① 在本包下写实现类 ② 在下面 `registry.register(...)` 一次。
核心框架、接口、诊断服务**均无需改动**——这是「加全天候不用从头再来」的落点。
"""

from app.services.strategy_engine.registry import registry
from app.services.strategy_engine.strategies.trend import TrendFollowingStrategy

registry.register(TrendFollowingStrategy())

__all__ = ['registry', 'TrendFollowingStrategy']

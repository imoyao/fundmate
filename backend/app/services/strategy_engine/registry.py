# -*- coding: utf-8 -*-
"""策略注册表（#2224）——插件式注册，新增策略零侵入核心。

WHY 注册表
    调用方（diagnosis / 未来的提醒 job）只按 code 取策略，**不 import 具体策略类**。
    于是加一个新策略 = 写一个类 + 在 `strategies/__init__.py` 里注册一次，
    框架、状态机、接口、测试脚手架全部不动——这是「加全天候不用从头再来」的落点。
"""

from __future__ import annotations

from typing import Iterable

from app.services.strategy_engine.contracts import BaseStrategy, StrategyFamily


class StrategyRegistry:
    """按 code 索引策略实例。策略是**无状态**的（求值输入全在 ctx），故可全局复用单例。"""

    def __init__(self) -> None:
        self._items: dict[str, BaseStrategy] = {}

    def register(self, strategy: BaseStrategy) -> BaseStrategy:
        code = strategy.meta.code
        if code in self._items:
            raise ValueError(f'策略 code 重复注册：{code}')
        self._items[code] = strategy
        return strategy

    def get(self, code: str) -> BaseStrategy | None:
        return self._items.get(code)

    def require(self, code: str) -> BaseStrategy:
        """取策略；不存在直接抛错（调用方传错 code 属编程错误，不静默降级）。"""
        strategy = self.get(code)
        if strategy is None:
            raise KeyError(f'未注册的策略：{code}')
        return strategy

    def all(self) -> list[BaseStrategy]:
        return list(self._items.values())

    def by_family(self, family: StrategyFamily) -> list[BaseStrategy]:
        return [s for s in self._items.values() if s.meta.family is family]

    def satisfiable(self, available: Iterable[str]) -> list[BaseStrategy]:
        """按**可用数据**筛选可跑的策略——数据不够的策略不出现在结果里（诚实降级）。"""
        supply = set(available)
        return [s for s in self._items.values() if s.meta.required_data <= supply]

    def codes(self) -> list[str]:
        return sorted(self._items)


#: 进程级单例。`strategies/__init__.py` 导入时完成注册。
registry = StrategyRegistry()

# -*- coding: utf-8 -*-
"""
@Time ： 2022/10/19 11:32
@File ：base.py
@IDE ：PyCharm
"""
from typing import Dict, Optional


class StrategyMeta(type):
    """
    定义元类：
    所有组合爬虫类必须实现detail方法以返回特定组合的持仓
    """

    def __new__(mcs, name, bases, namespace, **kwargs):
        if name != 'Base' and 'detail' not in namespace:
            raise TypeError('Bad StrategyMeta class!')
        return super().__new__(mcs, name, bases, namespace, **kwargs)


class StrategyBase(metaclass=StrategyMeta):
    """
    以下需要保证匹配：
    The return type
    The number of parameters
    The data type of one of the parameters
    The data structure of one of the parameters
    """

    def detail(self, code: str) -> Optional[Dict]:
        pass


class SB1(StrategyBase):
    def detail(self, code: str) -> Optional[Dict]:
        pass


if __name__ == '__main__':
    sb1 = SB1()
    sb1.detail(code='12345')

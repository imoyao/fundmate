#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/16 11:09
@file: combination.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 爬取蛋卷基金的基金组合并保存到数据库，为后期跟踪策略提供数据
"""


class Strategy:
    """
    以银行螺丝钉为例
    https://danjuanapp.com/strategy/CSI1033
    """

    def get(self):
        """获取所有组合"""
        pass

    def detail(self, code):
        """
        获取单个组合的信息
        :param code:
        :return:
        """
        pass

    def trade_history(self, code):
        """
        获取组合的调仓历史
        :param code:
        :return:
        """
        pass

    def net_worth(self, code):
        """
        获取基金的净值
        :param code:
        :return:
        """
        pass

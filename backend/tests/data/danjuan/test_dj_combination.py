#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/16 11:09
@file: test_dj_combination.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 测试好买基金组合接口
"""

from backend.fundmate.data.danjuan.combination import Strategy


class TestStrategy:
    """
    """

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.sty = Strategy()

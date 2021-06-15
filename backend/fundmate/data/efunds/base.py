#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/2/13 21:12
"""
基金类型获取
"""
import pandas as pd

url = 'https://e.efunds.com.cn/funds'


class ImportHistory:
    """导入投资历史
    1. 获取用户历史购买的所有基金
    2. 根据名称获取基金code
    3. 对于自动识别失败的基金名称，需要用户手动输入code
    4. 后台合并数据组
    5. 将数据导入数据库
    """

    def import_csv(self, file_path='demo.scv', sep=','):
        """
        读csv获取数据结果
        :return:
        """
        df = pd.read_csv(file_path, sep=sep)
        df.head()

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/1/19 18:06
@file: trans.py
@author: imoyao
@email: immoyao@gmail.com
@desc:
将理财记录原始数据处理为可以导入的统一数据
1. 导出数据应该为csv格式
2. 默认编码为gb18030，如果报错请修改
"""
from pathlib import Path

import pandas as pd

# 手机端
current_path = Path.cwd()
PC_FILE_NAME = ''
MOBILE_FILE_NAME = ''
PC_ALIPAY_RECORDS_FP = Path(current_path).joinpath(PC_FILE_NAME)
MOBILE_ALIPAY_RECORDS_FP = Path(current_path).joinpath(MOBILE_FILE_NAME)
encoding = 'gb18030'

mb_dt = pd.read_csv(MOBILE_ALIPAY_RECORDS_FP, header=1, encoding=encoding)
# ['收/支                 ',
#  '交易对方                ',
#  '对方账号                ',
#  '商品说明                ',
#  '收/付款方式              ',
#  '金额                  ',
#  '交易状态                ',
#  '交易分类                ',
#  '交易订单号     ',
#  '商家订单号           ',
#  '交易时间            ']
raw_columns_list = mb_dt.columns.to_list()[:-1]


def strip_column_name_readable(columns_list: list):
    return [column.strip() for column in columns_list]


if __name__ == '__main__':
    ret = strip_column_name_readable(raw_columns_list)
    print(ret)

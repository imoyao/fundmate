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

from backend.fundmate.types import PdDataFrame

# 手机端
current_path = Path.cwd()
PC_FILE_NAME = ''
MOBILE_FILE_NAME = ''
PC_ALIPAY_RECORDS_FP = Path(current_path).joinpath(PC_FILE_NAME)
MOBILE_ALIPAY_RECORDS_FP = Path(current_path).joinpath(MOBILE_FILE_NAME)
encoding = 'gb18030'


def get_raw_df():
    mb_df = pd.read_csv(MOBILE_ALIPAY_RECORDS_FP, header=1, encoding=encoding)
    return mb_df


# ['收/支',
#  '交易对方',
#  '对方账号',
#  '商品说明',
#  '收/付款方式',
#  '金额',
#  '交易状态',
#  '交易分类',
#  '交易订单号',
#  '商家订单号',
#  '交易时间']

mb_rename_list = [
    'op_type', 'trans_obj', 'trans_account', 'comment', 'pay_method', 'amount', 'status', 'trans_type', 'trans_code',
    'bus_code', 'trans_datetime'
]


def get_remove_unnamed_columns(raw_columns_list) -> list:
    if raw_columns_list[-2] == '交易时间':
        remove_unnamed_columns_list = raw_columns_list[:-1]
        return remove_unnamed_columns_list


def mk_rename_dict(remove_unnamed_columns_list: list) -> dict:
    """
    组装重命名的映射关系
    :return:
    """
    rename_dict = dict(zip(remove_unnamed_columns_list, mb_rename_list))
    return rename_dict


def strip_columns(with_space_columns_df: PdDataFrame) -> PdDataFrame:
    with_space_columns_df.columns = with_space_columns_df.columns.str.strip()
    return with_space_columns_df


def filter_invest_df(renamed_dt):
    """
    过滤出所有包含投资理财行为的交易数据
    :param renamed_dt:
    :return:
    """
    renamed_dt = renamed_dt[~renamed_dt.trans_type.isnull()]
    invest_df = renamed_dt.loc[renamed_dt['trans_type'].str.contains('投资理财')]
    return invest_df


def get_code_from_comment():
    """
    解析comment，获取交易的基金，从而调用接口获取交易的基金编码
    :return:
    """
    pass


def main():
    mb_df = get_raw_df()
    striped_columns = strip_columns(mb_df)
    raw_columns_list = striped_columns.columns.to_list()
    removed_unnamed_columns_list = get_remove_unnamed_columns(raw_columns_list)
    removed_unnamed_columns_df = mb_df[removed_unnamed_columns_list]
    rename_dict = mk_rename_dict(removed_unnamed_columns_list)
    renamed_dt = removed_unnamed_columns_df.rename(columns=rename_dict)
    invest_df = filter_invest_df(renamed_dt)
    return 0


if __name__ == '__main__':
    ret = main()
    print(ret)

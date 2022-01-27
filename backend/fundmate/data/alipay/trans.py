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

## 基本处理流程：
1. 读取原生文件
2. 表头whitespace切割
3. 删除df最后一个空列
4. 截取有用的数据集
5. 数据集重命名
6. 数据集去除 whitespace
7. 解析交易行为：获取交易性质、交易源产品、交易目标产品
"""
from pathlib import Path
from typing import Union

import pandas as pd

from backend.fundmate.excepts import NotSupportError
from backend.fundmate.settings import FundOpTypeEnum
from backend.fundmate.types import PdDataFrame

current_path = Path.cwd()
'''
手机端导出账单用户和PC端导出账单选择其一配置即可
'''
# PC: True MOBILE: False
IS_FROM_PC = False
# 手机端导出文件配置此处
MOBILE_FILE_NAME = 'alipay_record_20220119_173409.csv'
BASE_MOBILE_FILE_EXPORT_NAME = '手机端支付宝交易单导出.csv'
# PC端导出文件配置此处
PC_FILE_NAME = ''
BASE_PC_FILE_EXPORT_NAME = 'PC端支付宝交易单导出.csv'

# r'C:\Users\Andy\Desktop\alipay_record_20220119_173409\alipay_record_20220119_173409.csv'
PC_ALIPAY_RECORDS_FP = Path(current_path).joinpath(PC_FILE_NAME)
MOBILE_ALIPAY_RECORDS_FP = Path(current_path).joinpath(MOBILE_FILE_NAME)
PC_ALIPAY_EXPORT_FP = Path(current_path).joinpath(PC_FILE_NAME)
MOBILE_ALIPAY_EXPORT_FP = Path(current_path).joinpath(MOBILE_FILE_NAME)
encoding = 'gb18030'
CASH_NAME = '余额宝'
TRANSFER_SYMBOL = '[转换至]'
ANT_FORTUNE_SALE_TO_YEB = '卖出至余额宝'
ANT_FORTUNE_PURCHASE_STR = '买入'
ANT_FORTUNE_BONUS_TO_YEB = '现金分红至余额宝'
ANT_FORTUNE_COMB_TO_YEB = '转出至余额宝'
YUEBAO_LISTS = []
# WARNING：记录流水号涉及部分个人敏感数据上传，请确保使用时是自主配置该项
IS_RECORD_TRANSACTIONAL_NUMBER = False


def get_raw_df(raw_fp: Union[str, Path]) -> PdDataFrame:
    if raw_fp.exists() and raw_fp.is_file():
        mb_df = pd.read_csv(raw_fp, header=1, encoding=encoding)
        return mb_df
    else:
        raise FileNotFoundError('请正确配置导入的源文件路径！')


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
    """
    去除最后一列：未定义列
    :param raw_columns_list:
    :return:
    """
    if raw_columns_list[-2] == '交易时间':
        remove_unnamed_columns_list = raw_columns_list[:-1]
        return remove_unnamed_columns_list


def mk_rename_dict(remove_unnamed_columns_list: list) -> dict:
    """
    组装重命名的映射关系（中文转英文）
    :return:
    """
    rename_dict = dict(zip(remove_unnamed_columns_list, mb_rename_list))
    return rename_dict


def strip_columns(with_space_columns_df: PdDataFrame) -> PdDataFrame:
    """
    df去除表头 whitespace
    :param with_space_columns_df:
    :return:
    """
    with_space_columns_df.columns = with_space_columns_df.columns.str.strip()
    without_space_columns_df = with_space_columns_df.copy()
    return without_space_columns_df


def operate_fund(invest_df: PdDataFrame) -> PdDataFrame:
    """
    筛选其中赎购基金的操作
    :param invest_df: 
    :return: 
    """
    invest_df = invest_df.loc[invest_df['comment'].str.contains('蚂蚁财富')]
    return invest_df


def filter_invest_df(renamed_df: PdDataFrame) -> PdDataFrame:
    """
    过滤出所有包含"投资理财"行为的交易数据
    :param renamed_df:
    :return:
    """
    renamed_df = renamed_df[~renamed_df.trans_type.isnull()]
    invest_df = renamed_df[renamed_df.trans_type == '投资理财']
    # invest_df = renamed_df.loc[renamed_df['trans_type'].str.contains('投资理财')]
    return invest_df


def strip_df_values(df: PdDataFrame) -> PdDataFrame:
    """
    对df每一列进行切分去掉前后的空格和`\t`
    :return:
    """
    # see also:  https://stackoverflow.com/a/40950485/14295718
    cols = df.select_dtypes(object).columns
    df[cols] = df[cols].apply(lambda x: x.str.strip())
    return df


def analysis_operate(comment_info: str) -> tuple:
    """
    分割说明文字，解析交易行为
    FIXME: PY3.10 match-case
    """
    op_type, from_name, target_name = None, None, None
    comment_list = comment_info.split('-')
    comt_len = len(comment_list)
    if comt_len == 2:
        _, from2target = comment_list
        if TRANSFER_SYMBOL in from2target:
            '''
            一个转换行为实际由两部分组成：
            1. 从源产品卖出到现金
            2. 从现金买入目的产品
            '''
            from_name, target_name = from2target.split(TRANSFER_SYMBOL)
            op_type = FundOpTypeEnum.transfer
        else:
            raise NotSupportError(f'暂时无法处理交易行为：{comment_info}')
    elif comt_len == 3:
        _, mid_comt, tail_comt = comment_list
        # ['卖出至余额宝', '买入', '现金分红至余额宝', '转出至余额宝']
        if tail_comt == ANT_FORTUNE_COMB_TO_YEB:
            raise NotSupportError(f'暂时无法处理<组合卖出>：{comment_info}')
        elif tail_comt == ANT_FORTUNE_SALE_TO_YEB:
            from_name = mid_comt
            op_type = FundOpTypeEnum.sale.label
            target_name = CASH_NAME
        elif tail_comt == ANT_FORTUNE_PURCHASE_STR:
            from_name = CASH_NAME
            op_type = FundOpTypeEnum.purchase.label
            target_name = mid_comt
        elif tail_comt == ANT_FORTUNE_BONUS_TO_YEB:
            from_name = mid_comt
            op_type = FundOpTypeEnum.bonus.label
            target_name = CASH_NAME
        else:
            raise NotSupportError(f'暂时无法处理交易行为：{comment_info}, tail_comt:{tail_comt}')
    elif comt_len == 4:
        '''
        卖出退款，此时我们对重新买入产品不感兴趣
        '''
        _, from_name, raw_to_name, transfer_status = comment_list
        op_type = FundOpTypeEnum.transfer_refund.label
        target_name = CASH_NAME
    elif comt_len == 5:
        _, *mid_comt_split_list, tail_comt = comment_list
        if tail_comt == ANT_FORTUNE_SALE_TO_YEB:
            op_type = FundOpTypeEnum.sale.label
            # 易方达黄金主题(QDII-LOF-FOF)A
            from_name = '-'.join(mid_comt_split_list)
            target_name = CASH_NAME
        else:
            raise NotSupportError(f'暂时无法处理交易行为：{comment_info}')

    return op_type, from_name, target_name


def parse_comment(invest_df: PdDataFrame) -> PdDataFrame:
    """
    对原来的“商品说明”列进行解析拆分，从而获取交易类型（买入、卖出、分红等），交易品类（后续获取基金编码），
    `copy()`和下一行是为了解决如下warning:
    A value is trying to be set on a copy of a slice from a DataFrame.
    Try using .loc[row_indexer,col_indexer] = value instead
    :param invest_df:
    :return:
    """
    invest_df_cp = invest_df.copy()
    invest_df_cp.loc[:, 'comment'] = invest_df.comment
    invest_df_cp['op_type'] = invest_df_cp.comment.map(lambda x: analysis_operate(x)[0])
    invest_df_cp['from_prod'] = invest_df_cp.comment.map(lambda x: analysis_operate(x)[1])
    invest_df_cp['to_prod'] = invest_df_cp.comment.map(lambda x: analysis_operate(x)[2])
    return invest_df_cp


def get_code_from_comment():
    """
    解析comment，获取交易的基金，从而调用接口获取交易的基金编码
    :return:
    """
    pass


def pre_prepared_df(df: PdDataFrame) -> PdDataFrame:
    """
    对脏数据进行预处理：
    ## 行：
    1. 去掉表头的 whitespace
    2. 去掉尾部注释性文字（包含用户隐私数据）
    ## 列：
    1. 去掉最后一列无意义空列
    :param df:
    :return:
    """
    striped_columns_df = strip_columns(df)
    raw_columns_list = striped_columns_df.columns.to_list()
    removed_unnamed_columns_list = get_remove_unnamed_columns(raw_columns_list)
    removed_unnamed_columns_df = striped_columns_df[removed_unnamed_columns_list]
    rename_dict = mk_rename_dict(removed_unnamed_columns_list)
    renamed_df = removed_unnamed_columns_df.rename(columns=rename_dict)

    useful_df = df_drop_useless_tail(renamed_df)
    return useful_df


def df_drop_useless_tail(df: PdDataFrame, n: int = 20):
    """
    删除n尾行
    :param df:
    :param n:
    :return:
    """
    df.drop(df.tail(n).index, inplace=True)  # drop last n rows
    return df


def main():
    """

    :return:
    """
    raw_df = get_raw_df()

    useful_df = pre_prepared_df(raw_df)
    # 只保留基金交易数据
    striped_df = strip_df_values(useful_df)
    invest_df = filter_invest_df(striped_df)

    analysis_df = parse_comment(invest_df)
    # 根据用户意愿删除流水号
    if not IS_RECORD_TRANSACTIONAL_NUMBER:
        analysis_df.drop(columns='trans_code', inplace=True)

    if IS_FROM_PC:
        analysis_df.to_csv(PC_ALIPAY_EXPORT_FP, index=False)
    else:
        analysis_df.to_csv(MOBILE_ALIPAY_EXPORT_FP, index=False)
    return 0


if __name__ == '__main__':
    ret = main()
    print(ret)

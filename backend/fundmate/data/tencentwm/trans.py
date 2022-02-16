#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/2/11 10:53
@file: trans.py
@author: imoyao
@email: immoyao@gmail.com
@desc:
用于把导出的源文件处理为统一的交易流水账单
TODO:
1. PUR_TYPE_MAPS 和 PAY_CHANNEL_MAPS 需要补充
2. 表头需要补充理解
3. 描述需要对照补充
4. 代码整理，需要封装为类
"""
from pathlib import Path
from typing import Union

import dateparser
import pandas as pd
import pyjson5

from backend.fundmate.excepts import NotSupportError
from backend.fundmate.settings import BaseTypeEnum, FundOpTypeEnum
from backend.fundmate.types import PdDataFrame

current_path = Path.cwd()
TEMPLATE_FILE_NAME = 'record.json'
LCT_RECORDS_TEMPLATE_FP = Path(current_path).joinpath(TEMPLATE_FILE_NAME)
USEFUL_COLUMNS = [
    'acc_time',
    'fund_trans_id',
    'fund_type',
    'fund_code',
    'partner_nickname',
    'pur_type',
    'pay_channel',
    'receive_type',
    'state',
    'real_redem_amt',
    'refund_fee',
    'total_fee',
]
'''
['acc_time',        # 交易时间
 'busi_flag',
 'business_type',
 'close_id',
 'end_date',
 'ex_process_fee',
 'fund_code',       # 基金编码
 'fund_flow',
 'fund_trans_id',       # 交易流水编码
 'fund_type',           # 基金类型
 'issue',
 'opt_type',
 'partner_id',
 'partner_nickname',    # 基金名称
 'pay_channel',
 'plan_type',
 'plat_type',
 'product_code',
 'profit_bits',
 'pur_type',
 'purpose',
 'real_redem_amt',      # 购买的份额
 'receive_type',
 'redem_ack_date',
 'redem_cash_date',
 'refund_fee',      # 退款费用（分）
 'refund_reason',
 'refund_type',
 'sp_purpose',
 'spe_tag',
 'state',
 'sub_code',
 'total_fee',       # 交易金额（分）
 'trade_cancel_type',
 'trade_date',
 'union_id',
 'unit_accuracy',   # 精度，0和100的区别是什么没看出来
 'voucher_fee',
 'withdraw_type']
'''

# WARNING：记录流水号涉及部分个人敏感数据上传，请确保使用时是自主配置该项
IS_RECORD_TRANSACTIONAL_NUMBER = True
# ============变量配置===============
BASE_EXPORT_FILE_NAME = '理财通交易单导出.csv'
YUE_PLUS_NAME = '余额+'
fund_types = {"1": "低风险", "2": "中低风险", "4": "中高风险", "7": "保险理财产品", "3": "中低风险保险理财产品", "11": "人保财险理财产品", "5": "P2P理财产品"}
# business_type_map = {
#     '0': '买入',
#     '27': '投顾服务费',
# }
# ['4', '1', '12', '11', '22', '25', '13', '14', '21', '10', '24',
#        '29', '20', '18']
# 需要继续补充
PUR_TYPE_MAPS = {
    '1': '余额+买入',
    '4': '快速取出',
    '11': '转入(取出到余额+)',
    '12': '取出到余额+',
    '13': '红利再投',
    '14': '现金分红',
    '10': '赠送红包到账',
    '18': '从余额+买入',
    '20': '人保财险',  # 我靠！
    '21': '银行卡买入余额+',
    '22': '普通取出',
    '24': '零钱通买入基金组合',
    '25': '普通取出到余额+',
    '29': '组合调仓（需要关注手续费）',
}
PAY_CHANNEL_MAPS = {
    '0': '快速取出',
    '1': '余额买入',
    '3': '赠送红包买入',
    '4': '银行卡买入(通过工资理财)',
    '5': '从信诚薪金宝',
    '6': '产品取出到余额+买入',
    '8': '退款买入',
    '9': '零钱通买入',
    '10': '撤单退款到余额+',
    '16': '赠送红包买入',
    '18': '转投（买入）',
    '20': '买入（通过现金分红）',
    '22': '从其他产品买入',
    '26': '银行卡买入',
    '30': '银行卡买入余额+',
}

RENAME_COLUMNS_DICT = {
    'acc_time': '交易时间',
    'fund_trans_id': '渠道交易流水号',
    'fund_type': '产品类型',
    'fund_code': '产品编码',
    'partner_nickname': '产品名称',
    'from_prod': '卖出产品',
    'to_prod': '买入产品',
    'pur_type': '交易类型',
    'pay_channel': '交易方式',
    'refund_fee': '退款费用',
    'total_fee': '交易金额',
    'comment': '商品说明',
    'op_type': '程序描述标识',
    'op_type_read': '交易类型',
    'op_type_desc': '交易类型描述',
    'trans_cost': '服务费（元）',
}

# refund_type = 12 意味着退款
REVOKE_STATE = '23'


def read_raw_data(fp: Union[str, Path]) -> PdDataFrame:
    with open(fp, encoding='utf-8') as f:
        json_raw_str = pyjson5.load(f)
    df = pd.DataFrame(json_raw_str)
    return df


def change_to_user_friendly(op_type: BaseTypeEnum):
    """
    根据comment转换为用户可读的内容
    :param op_type:
    :return:
    """
    if op_type:
        op_desc = op_type.label
        op_name = op_type.name
        op_input = op_desc  # TODO: op_desc没有必要存在了
        return {
            'name': op_name,
            'desc': op_desc,
            'input': op_input,
        }
    return {
        'name': None,
        'desc': None,
        'input': None,
    }


def pretty_result(df: PdDataFrame) -> PdDataFrame:
    """
    对数据项进行处理，以使显示结果更加明晰
    :param df:
    :return:
    """

    def divide_100_to_clear(x: int) -> float:
        return x / 100

    df['fund_code'] = df['fund_code'].astype(str)
    df['refund_fee'] = df.refund_fee.apply(lambda refund_fee: divide_100_to_clear(int(refund_fee)))
    df['total_fee'] = df.total_fee.apply(lambda fee: divide_100_to_clear(int(fee)))
    return df


def transfer_pay_channel(pay_channel: str, receive_type: str, pur_type: str, state: str) -> PdDataFrame:
    """
    此处对应关系复杂，后续需要继续排查
    :param pay_channel:
    :param receive_type:
    :param pur_type:
    :param state:
    :return:
    """
    if pay_channel in PAY_CHANNEL_MAPS:
        if state == REVOKE_STATE:
            op_type = FundOpTypeEnum.revoke
        else:
            if pay_channel == '0':
                if pur_type == '4':
                    if receive_type == '2':
                        op_type = FundOpTypeEnum.draw_out
                    elif receive_type == '1':
                        op_type = FundOpTypeEnum.sale
                elif pur_type == '13':
                    op_type = FundOpTypeEnum.quot_bonus
                elif pur_type == '14':
                    op_type = FundOpTypeEnum.cash_bonus
                elif pur_type == '22':
                    op_type = FundOpTypeEnum.draw_out
                else:
                    op_type = FundOpTypeEnum.sale
            elif pay_channel in ['4', '5', '9', '26', '30']:
                op_type = FundOpTypeEnum.deposit
                if pur_type == '11':
                    op_type = FundOpTypeEnum.regular_invest
            elif pay_channel in ['1', '3', '6', '8', '10', '16', '18', '20', '22']:
                op_type = FundOpTypeEnum.purchase
            else:
                raise NotSupportError(f'目前不支持交易类型——pay_channel：{pay_channel}')
        return op_type
    else:
        raise NotSupportError(f'目前不支持交易类型——pay_channel：{pay_channel}')


def join_new_comment(pay_channel_comment: str, pur_type_comment: str) -> str:
    """
    将两段comment合并
    :param pay_channel_comment:
    :param pur_type_comment:
    :return:
    """
    if pay_channel_comment == pur_type_comment:
        return pay_channel_comment
    return '-'.join([pay_channel_comment, pur_type_comment])


def parse_trade_df(df: PdDataFrame) -> PdDataFrame:
    filtered_df = df[USEFUL_COLUMNS]
    filtered_df_cp = filtered_df.copy()
    filtered_df_cp.loc[:, 'pay_channel'] = filtered_df.pay_channel
    filtered_df_cp.loc[:, 'pur_type'] = filtered_df.pur_type
    filtered_df_cp['pay_channel_comment'] = filtered_df_cp.pay_channel.apply(lambda x: PAY_CHANNEL_MAPS.get(x, None))
    filtered_df_cp['pur_type_comment'] = filtered_df_cp.pur_type.apply(lambda x: PUR_TYPE_MAPS.get(x, None))
    # 根据pay_channel 匹配交易行为
    filtered_df_cp.loc[:, 'comment'] = filtered_df.apply(
        lambda row: transfer_pay_channel(row['pay_channel'], row['receive_type'], row['pur_type'], row['state']),
        axis=1)
    filtered_df_cp['op_type'] = filtered_df_cp.comment.map(lambda x: change_to_user_friendly(x).get('name'))
    filtered_df_cp['op_type_read'] = filtered_df_cp.comment.map(lambda x: change_to_user_friendly(x).get('input'))
    filtered_df_cp['op_type_desc'] = filtered_df_cp.comment.map(lambda x: change_to_user_friendly(x).get('desc'))

    filtered_df_cp.loc[:, 'comment'] = filtered_df_cp.apply(
        lambda row: join_new_comment(row['pay_channel_comment'], row['pur_type_comment']), axis=1)

    # 交易状态确定后，删除以下字段
    drop_columns = [
        'real_redem_amt', 'fund_type', 'pay_channel', 'receive_type', 'pur_type', 'state', 'pay_channel_comment',
        'pur_type_comment'
    ]
    filtered_df_cp.drop(columns=drop_columns, inplace=True)

    clarified_df = pretty_result(filtered_df_cp)
    if not IS_RECORD_TRANSACTIONAL_NUMBER:
        clarified_df.drop(columns=['fund_trans_id'], inplace=True)
    else:
        clarified_df['fund_trans_id'] = clarified_df.fund_trans_id.apply(lambda x: x + '\t')

    # 添加交易手续费字段
    clarified_df['trans_cost'] = 0
    return clarified_df


def get_datetime_dict(df):

    def mk_date(date_str: str):
        """
        :return:
        """
        date_inst = dateparser.parse(date_str)
        return f'{date_inst.year}{date_inst.month:02}{date_inst.day:02}-{date_inst.hour:02}{date_inst.minute:02}{date_inst.second:02}'

    start = df.iloc[0, :]['acc_time']
    end = df.iloc[-1, :]['acc_time']
    start_date = mk_date(start)
    end_date = mk_date(end)
    date_list = [start_date, end_date]
    date_dict = dict(zip(['start_datetime', 'end_datetime'], date_list))
    return date_dict


def main():
    df = read_raw_data(LCT_RECORDS_TEMPLATE_FP)
    parsed_df = parse_trade_df(df)
    date_dict = get_datetime_dict(parsed_df)
    prefix = f'起始时间[{date_dict.get("start_datetime")}]-终止时间[{date_dict.get("end_datetime")}]'
    with_date_name = f'{prefix}-{BASE_EXPORT_FILE_NAME}'
    export_fp = Path(current_path).joinpath(with_date_name)
    renamed_df = parsed_df.rename(columns=RENAME_COLUMNS_DICT)
    renamed_df.to_csv(export_fp, index=False)
    return renamed_df


if __name__ == '__main__':
    main()

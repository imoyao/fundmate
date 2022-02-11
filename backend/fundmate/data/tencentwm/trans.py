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
from typing import Dict, List, Optional, Union

import dateparser
import pandas as pd
import pyjson5

from backend.fundmate.types import PdDataFrame

current_path = Path.cwd()
TEMPLATE_FILE_NAME = 'record.json'
LCT_RECORDS_TEMPLATE_FP = Path(current_path).joinpath(TEMPLATE_FILE_NAME)
USEFUL_COLUMNS = [
    'acc_time',
    'fund_code',
    'fund_trans_id',
    'fund_type',
    'fund_code',
    'partner_nickname',
    'pur_type',
    'pay_channel',
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
# ============变量配置===============
BASE_EXPORT_FILE_NAME = '理财通交易单导出.csv'
YUE_PLUS_NAME = '余额+'
fund_types = {"1": "低风险", "2": "中低风险", "4": "中高风险", "7": "保险理财产品", "3": "中低风险保险理财产品", "11": "人保财险理财产品", "5": "P2P理财产品"}
business_type_map = {
    '0': '买入',
    '27': '投顾服务费',
}
# ['0', '6', '4', '18', '5', '22', '8', '26', '20', '30', '16', '9',
#        '10', '3', '1']
'''
<select id="trans_pur_type_select">
    <option value="all">全部</option>
    <option value="1">买入</option>
    <option value="2">取出</option>
</select>
'''
# ['4', '1', '12', '11', '22', '25', '13', '14', '21', '10', '24',
#        '29', '20', '18']
# 需要继续补充
PUR_TYPE_MAPS = {
    '1': '余额+买入',
    '4': '快速取出',
    '11': '买入转入(取出到余额+)',
    '12': '从理财通余额+ 取出',
    '13': '红利再投',
    '14': '现金分红',
    '10': '赠送红包到账',
    '18': '从余额+买入',
    '20': '人保财险',  # 我靠！
    '21': '银行卡买入余额+',
    '22': '快速取出',
    '24': '零钱通买入基金组合',
    '25': '普通取出到余额+',
    '29': '组合调仓（需要关注手续费）',
}
PAY_CHANNEL_MAPS = {
    '0': '快速取出',
    '1': '余额买入',
    '3': '赠送红包买入',
    '16': '赠送红包买入',
    '4': '银行卡买入(通过工资理财)',
    '5': '从信诚薪金宝买入',
    '6': '产品取出到余额+买入',
    '8': '退款买入',
    '9': '零钱通买入',
    '10': '撤单退款到余额+',
    '18': '转投（买入）',
    '20': '买入（通过现金分红）',
    '22': '从其他产品买入',
    '26': '银行卡买入',
    '30': '银行卡买入余额+',
}

# refund_type = 12 意味着退款


def read_raw_data(fp: Union[str, Path]) -> PdDataFrame:
    with open(fp, encoding='utf-8') as f:
        json_raw_str = pyjson5.load(f)
    df = pd.DataFrame(json_raw_str)
    return df


def parse_trade_df(df):
    filtered_df = df[USEFUL_COLUMNS]
    filtered_df_cp = filtered_df.copy()
    filtered_df_cp.loc[:, 'pay_channel'] = filtered_df.pay_channel
    filtered_df_cp.loc[:, 'pur_type'] = filtered_df.pur_type
    filtered_df_cp['pay_channel_comment'] = filtered_df_cp.pay_channel.apply(lambda x: PAY_CHANNEL_MAPS.get(x, None))
    filtered_df_cp['pur_type_comment'] = filtered_df_cp.pur_type.apply(lambda x: PUR_TYPE_MAPS.get(x, None))
    return filtered_df_cp


# def sort_by_date(df):
#     df['acc_time'] = pd.to_datetime(df.acc_time)
#     df.index = df['acc_time']
#     df.sort_index()
#     return df


def get_datetime_dict(df):

    def mk_date(date_str: str):
        """
        2021/12/31-235959
        :param date_tuple:
        :return:
        """
        date_inst = dateparser.parse(date_str)
        return f'{date_inst.year}{date_inst.month:02}{date_inst.day:02}-{date_inst.hour:02}{date_inst.minute:02}{date_inst.second:02}'

    start = df.iloc[0, :]['acc_time']
    end = df.iloc[-1, :]['acc_time']
    start_date = mk_date(start)
    end_date = mk_date(end)
    date_list = [start_date, end_date]
    print(date_list)
    date_dict = dict(zip(['start_datetime', 'end_datetime'], date_list))
    return date_dict


def main():
    df = read_raw_data(LCT_RECORDS_TEMPLATE_FP)
    parsed_df = parse_trade_df(df)
    date_dict = get_datetime_dict(parsed_df)
    prefix = f'起始时间[{date_dict.get("start_datetime")}]-终止时间[{date_dict.get("end_datetime")}]'
    with_date_name = f'{prefix}-{BASE_EXPORT_FILE_NAME}'
    export_fp = Path(current_path).joinpath(with_date_name)
    print(export_fp)
    parsed_df.to_csv(export_fp, index=False)
    return parsed_df


if __name__ == '__main__':
    main()

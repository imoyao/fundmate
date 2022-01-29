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
TODO:
1. 银行卡转入转出和账户内买入卖出需要区分开！！！
"""
import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Union

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

# ============手机端导出文件配置此处==============
# MOBILE_FILE_NAME = 'alipay_record_20220119_173409.csv'
MOBILE_FILE_NAME = 'alipay_record_20220128_161121.csv'
# MOBILE_FILE_NAME = 'alipay_record_20220128_161241.csv'
BASE_MOBILE_FILE_EXPORT_NAME = '手机端支付宝交易单导出.csv'
MOBILE_ALIPAY_RECORDS_FP = Path(current_path).joinpath(MOBILE_FILE_NAME)
MOBILE_ALIPAY_EXPORT_FP = Path(current_path).joinpath(BASE_MOBILE_FILE_EXPORT_NAME)
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

MB_RENAME_LIST = [
    'op_type', 'trans_obj', 'trans_account', 'comment', 'pay_method', 'amount', 'status', 'trans_type', 'trans_code',
    'bus_code', 'trans_datetime'
]
# 重命名为普通用户可以看明白的表头
# TODO: 调整列的顺序
MB_OUTPUT_COLUMNS = {
    'op_type_read': '交易类型',
    'op_type_desc': '交易类型描述',
    'from_prod': '卖出产品',
    'to_prod': '买入产品',
    'amount': '交易金额',
    'trans_datetime': '交易时间',
    'trans_code': '渠道交易流水号',
    'comment': '商品说明',
    'pay_method': '交易方式',
    'op_type': '程序描述标识',
}
# 需要删除的字段列
MOBILE_DROP_COLUMNS = ['trans_obj', 'trans_account', 'status', 'trans_type', 'bus_code']
# =========PC端导出文件配置此处=========
PC_FILE_NAME = 'alipay_record_20220119_1630_1.csv'
BASE_PC_FILE_EXPORT_NAME = 'PC端支付宝交易单导出.csv'
PC_DROP_COLUMNS = ['trans_create_time', 'trans_pay_time', 'trans_dist', 'trans_refund', 'trans_type', 'bus_code']
PC_OUTPUT_COLUMNS = {
    'op_type_read': '交易类型',
    'op_type_desc': '交易类型描述',
    'from_prod': '卖出产品',
    'to_prod': '买入产品',
    'amount': '交易金额',
    'trans_datetime': '交易时间',
    'trans_code': '渠道交易流水号',
    'comment': '商品说明',
    'pay_method': '交易方式',
    'op_type': '程序描述标识',
}

# r'C:\Users\Andy\Desktop\alipay_record_20220119_173409\alipay_record_20220119_173409.csv'
PC_ALIPAY_RECORDS_FP = Path(current_path).joinpath(PC_FILE_NAME)
PC_ALIPAY_EXPORT_FP = Path(current_path).joinpath(BASE_PC_FILE_EXPORT_NAME)

ENCODING = 'gb18030'
YEB_NAME = '余额宝'  # 余额宝，背后为货币基金
YLB_NAME = '余利宝'  # 背后为货币基金
HB_NAME = '红包'  # 背后为货币基金
FILTER_INVEST_DATA_STR = '投资理财'
ANT_FORTUNE_STR = '蚂蚁财富'
# ===============手机端匹配字符==================
MB_LAST_COLUMNS_STR = '交易时间'
'''
每一次`ANT_FORTUNE_TRANSFER_YEB_STR` 都需要两种产品替换该字段
'''
YEB_NAME_OLD = '旧余额宝货币基金产品名'  # 需要导出文件后手动修改
YEB_NAME_NEW = '新余额宝货币基金产品名'  # 需要导出文件后手动修改
REAL_CASH = '现金'  # 即余额（可能是羊毛红包，也可能是好友转账转入）
TRANSFER_SYMBOL = '[转换至]'
ANT_FORTUNE_SALE_TO_YEB = '卖出至余额宝'
ANT_FORTUNE_PURCHASE_STR = '买入'
ANT_FORTUNE_HB_REWARD_PURCHASE_STR = '红包奖励发放'
ANT_FORTUNE_BONUS_TO_YEB = '现金分红至余额宝'
# 网商银行卡计息
ANT_FORTUNE_WS_INTEREST_TO_YEB = '账户结息'
ANT_FORTUNE_SALE_PROD_TO_YEB = '理财赎回'
ANT_FORTUNE_PURCHASE_YEB_TO_PROD = '理财买入'
ANT_FORTUNE_COMB_TO_YEB = '转出至余额宝'
ANT_FORTUNE_COMB_YEB_TO_YE = '转出到余额'
ANT_FORTUNE_AUTO_TO_YEB = '自动转入'
ANT_FORTUNE_RE_BUY_TO_YEB = '收益发放'
ANT_FORTUNE_PURCHASE_FUND_STR = '基金申购'

ANT_FORTUNE_CHALLENGE_RATE_TO_YEB = '收益挑战'
ANT_FORTUNE_CHALLENGE_PURCHASE_STR = '挑战包买入'
ANT_FORTUNE_CHALLENGE_SALE_STR = '挑战包卖出'

ANT_FORTUNE_REGULAR_INVEST_STR = '定期理财'
ANT_FORTUNE_REGULAR_INVEST_SALE_STR = '定期理财赎回'

ANT_FORTUNE_OUT_TO_BANK_CARD = '转出到银行卡'
ANT_FORTUNE_BANK_CARD_IN_STR = '银行卡转入'
ANT_FORTUNE_YLB_TO_YEB_YE = '余利宝转出到支付宝'
ANT_FORTUNE_YEB_YE_TO_YLB = '支付宝转入到余利宝'
ANT_FORTUNE_RECEIVED_TO_YEB = '转账收款到余额宝'
ANT_FORTUNE_BANK_CARD_TO_YEB = '单次转入'
ANT_FORTUNE_BANK_CARD_BIG_TO_YEB = '大额转入'
ANT_FORTUNE_BANK_CARD_SALARY_TO_YEB = '工资理财'
ANT_FORTUNE_MYXY_MANUAL_TO_YEB = '蚂蚁星愿主动攒入'
ANT_FORTUNE_MYXY_AUTO_TO_YEB = '蚂蚁星愿自动攒入'
ANT_FORTUNE_QIAN_MGR_TO_YEB = '钱管家转入'
ANT_FORTUNE_TRANSFER_YEB_STR = '更换货基转入'
ANT_FORTUNE_BBZ_PART1_STR = '笔笔攒'
ANT_FORTUNE_BBZ_PART2_STR = '单笔攒入'
USER_INPUT_EXCEL_DICT = {'purchase': '买入', 'sale': '卖出', 'transfer': '转换'}
# ===========PC端================
PC_LAST_COLUMNS_STR = '资金状态'
'''
['交易号',
 '商家订单号',
 '交易创建时间',
 '付款时间',
 '最近修改时间',
 '交易来源地',
 '类型',
 '交易对方',
 '商品名称',
 '金额（元）',
 '收/支',
 '交易状态',
 '服务费（元）',
 '成功退款（元）',
 '备注',
 '资金状态']
'''
PC_RENAME_LIST = [
    'trans_code', 'bus_code', 'trans_create_time', 'trans_pay_time', 'trans_modify_time', 'trans_source', 'trans_type',
    'trans_dist', 'comment', 'amount', 'op_type', 'status', 'trans_cost', 'trans_refund', 'user_comment',
    'assert_status'
]

YUEBAO_LISTS = []
# WARNING：记录流水号涉及部分个人敏感数据上传，请确保使用时是自主配置该项
IS_RECORD_TRANSACTIONAL_NUMBER = True


class ALiPayTransfer:

    def get_raw_df(self, raw_fp: Union[str, Path], header: int = 1) -> PdDataFrame:
        if raw_fp.exists() and raw_fp.is_file():
            mb_df = pd.read_csv(raw_fp, header=header, encoding=ENCODING)
            return mb_df
        else:
            raise FileNotFoundError(f'文件{raw_fp}未找到，请正确配置导入的源文件路径！')

    def strip_columns(self, with_space_columns_df: PdDataFrame) -> PdDataFrame:
        """
        df去除表头 whitespace
        :param with_space_columns_df:
        :return:
        """
        with_space_columns_df.columns = with_space_columns_df.columns.str.strip()
        without_space_columns_df = with_space_columns_df.copy()
        return without_space_columns_df

    def pre_prepared_df(self, df: PdDataFrame, last_columns_str: str = MB_LAST_COLUMNS_STR) -> PdDataFrame:
        """
        对脏数据进行预处理：
        ## 行：
        去掉表头的 whitespace
        ## 列：
        1. 去掉最后一列无意义空列
        :param last_columns_str:
        :param df:
        :return:
        """
        striped_columns_df = self.strip_columns(df)
        raw_columns_list = striped_columns_df.columns.to_list()
        removed_unnamed_columns_list = self.get_remove_unnamed_columns(raw_columns_list,
                                                                       last_columns_str=last_columns_str)
        removed_unnamed_columns_df = striped_columns_df[removed_unnamed_columns_list]
        rename_dict = self.mk_rename_dict(removed_unnamed_columns_list)
        renamed_df = removed_unnamed_columns_df.rename(columns=rename_dict)
        return renamed_df

    def get_remove_unnamed_columns(self, raw_columns_list: list, last_columns_str: str = MB_LAST_COLUMNS_STR) -> list:
        """
        去除最后一列：未定义列
        :param last_columns_str:
        :param raw_columns_list:
        :return:
        """
        if raw_columns_list[-2] == last_columns_str:
            remove_unnamed_columns_list = raw_columns_list[:-1]
            return remove_unnamed_columns_list

    def mk_rename_dict(self, remove_unnamed_columns_list: list, rename_list=None) -> dict:
        """
        组装重命名的映射关系（中文转英文）
        :return:
        """
        if rename_list is None:
            rename_list = MB_RENAME_LIST
        rename_dict = dict(zip(remove_unnamed_columns_list, rename_list))
        return rename_dict

    def get_durations(self, datetime_text: str) -> Optional[Dict]:
        """ 获取账单起止日期"""

        # 起始时间：[2021-01-01 00:00:00]    终止时间：[2021-12-31 23:59:59]
        # datetime_text = dt.iloc[-16:-15]['op_type'].to_list()[0]
        data_reg = r'([0-2][0-9]{3})\-(0[1-9]|1[0-2])\-([0-2][0-9]|3[0-1]) ([0-1][0-9]|2[0-3]):([0-5][0-9])\:([0-5][' \
                   r'0-9])( ([\-\+]([0-1][0-9])\:([0-5][0-9])))?'
        reg_mat = re.findall(data_reg, datetime_text)

        def mk_date(date_tuple: tuple):
            """
            2021/12/31-235959
            :param date_tuple:
            :return:
            """
            return f'{date_tuple[0]}{date_tuple[1]}{date_tuple[2]}-{date_tuple[3]}{date_tuple[4]}{date_tuple[5]}'

        date_dict = None
        if reg_mat:
            date_list = list()
            for date_item in reg_mat:
                reformat_datetime = mk_date(date_item)
                date_list.append(reformat_datetime)
            date_dict = dict(zip(['start_datetime', 'end_datetime'], date_list))
        return date_dict

    def df_drop_useless_tail(self, df: PdDataFrame, drop_tail_line_index: int = 20):
        """
        删除n尾行
        :param df:
        :param n:
        :return:
        """
        df.drop(df.tail(drop_tail_line_index).index, inplace=True)  # drop last n rows
        return df

    def strip_df_values(self, df: PdDataFrame) -> PdDataFrame:
        """
        对df每一列进行切分去掉前后的空格和`\t`
        :return:
        """
        # see also:  https://stackoverflow.com/a/40950485/14295718
        cols = df.select_dtypes(object).columns
        df[cols] = df[cols].apply(lambda x: x.str.strip())
        return df

    def _deal_transfer(self, comment_str: str) -> tuple:
        """
        处理基金转换的操作
        :param comment_str:
        :return:
        """
        comment_list = comment_str.split('-')
        split_head, from2target = comment_list
        if TRANSFER_SYMBOL in from2target:
            '''
            一个转换行为实际由两部分组成：
            1. 从源产品卖出到现金
            2. 从现金买入目的产品
            '''
            from_name, target_name = from2target.split(TRANSFER_SYMBOL)
            op_type = FundOpTypeEnum.transfer
        elif from2target in [
                ANT_FORTUNE_AUTO_TO_YEB, ANT_FORTUNE_BANK_CARD_TO_YEB, ANT_FORTUNE_SALE_TO_YEB,
                ANT_FORTUNE_QIAN_MGR_TO_YEB, ANT_FORTUNE_BANK_CARD_BIG_TO_YEB, ANT_FORTUNE_BANK_CARD_SALARY_TO_YEB,
                ANT_FORTUNE_BANK_CARD_IN_STR
        ]:
            from_name = REAL_CASH
            op_type = FundOpTypeEnum.purchase
            if split_head != YLB_NAME:
                # 1. 发的小红包/好友转账、2. 主动转入 3. 黄金票等提现（也是红包）4. 银行卡定期扣款
                target_name = YEB_NAME
            else:
                target_name = YLB_NAME
        elif from2target in [
                ANT_FORTUNE_OUT_TO_BANK_CARD, ANT_FORTUNE_COMB_YEB_TO_YE, ANT_FORTUNE_MYXY_MANUAL_TO_YEB,
                ANT_FORTUNE_MYXY_AUTO_TO_YEB
        ]:
            from_name = YEB_NAME
            op_type = FundOpTypeEnum.sale
            target_name = REAL_CASH
        elif from2target == ANT_FORTUNE_TRANSFER_YEB_STR:
            from_name = YEB_NAME_OLD
            op_type = FundOpTypeEnum.transfer
            target_name = YEB_NAME_NEW
        elif split_head in [ANT_FORTUNE_YLB_TO_YEB_YE, ANT_FORTUNE_WS_INTEREST_TO_YEB]:
            from_name = REAL_CASH
            op_type = FundOpTypeEnum.purchase
            target_name = YEB_NAME
        elif split_head in [ANT_FORTUNE_SALE_PROD_TO_YEB, ANT_FORTUNE_REGULAR_INVEST_SALE_STR]:
            from_name = f'理财产品<{from2target}>'
            op_type = FundOpTypeEnum.sale
            target_name = YEB_NAME
        elif split_head in [ANT_FORTUNE_PURCHASE_YEB_TO_PROD, ANT_FORTUNE_REGULAR_INVEST_STR]:
            from_name = YEB_NAME
            op_type = FundOpTypeEnum.purchase
            target_name = f'理财产品<{from2target}>'
        elif split_head == ANT_FORTUNE_YEB_YE_TO_YLB:
            if from2target == ANT_FORTUNE_PURCHASE_FUND_STR:
                from_name = REAL_CASH
                op_type = FundOpTypeEnum.sale
                target_name = YLB_NAME
            else:
                raise NotSupportError(f'暂时无法处理交易行为：{comment_str}')
        elif split_head == ANT_FORTUNE_CHALLENGE_RATE_TO_YEB:
            # FIXME:收益挑战实际是从产品卖出到余额宝的过程
            if ANT_FORTUNE_CHALLENGE_SALE_STR in from2target:
                from_name = REAL_CASH
                op_type = FundOpTypeEnum.sale
                target_name = YEB_NAME
            elif ANT_FORTUNE_CHALLENGE_PURCHASE_STR in from2target:
                from_name = REAL_CASH
                op_type = FundOpTypeEnum.purchase
                target_name = YEB_NAME
            else:
                raise NotSupportError(f'暂时无法处理交易行为：{comment_str}')
        else:
            raise NotSupportError(f'暂时无法处理交易行为：{comment_str}')
        return op_type, from_name, target_name

    def _deal_enum_operate(self, comment_str: str) -> tuple:
        """
        买入、分红、卖出操作
        :param comment_str:
        :return:
        """
        comment_list = comment_str.split('-')
        head_comt, mid_comt, tail_comt = comment_list
        # ['卖出至余额宝', '买入', '现金分红至余额宝', '转出至余额宝']
        if tail_comt == ANT_FORTUNE_COMB_TO_YEB:
            from_name = f'组合产品<{mid_comt}>'
            op_type = FundOpTypeEnum.purchase
            target_name = YEB_NAME
            # raise NotSupportError(f'暂时无法处理<组合卖出>：{comment_str}')
        elif tail_comt == ANT_FORTUNE_SALE_TO_YEB:
            from_name = mid_comt
            op_type = FundOpTypeEnum.sale
            target_name = YEB_NAME
        elif tail_comt == ANT_FORTUNE_PURCHASE_STR:
            from_name = YEB_NAME
            op_type = FundOpTypeEnum.purchase
            target_name = mid_comt
        elif tail_comt == ANT_FORTUNE_BONUS_TO_YEB:
            from_name = mid_comt
            op_type = FundOpTypeEnum.bonus
            target_name = YEB_NAME
        elif tail_comt in [ANT_FORTUNE_RE_BUY_TO_YEB, ANT_FORTUNE_BANK_CARD_SALARY_TO_YEB]:
            from_name = REAL_CASH
            op_type = FundOpTypeEnum.purchase
            target_name = YEB_NAME
        elif mid_comt == ANT_FORTUNE_BBZ_PART1_STR and tail_comt == ANT_FORTUNE_BBZ_PART2_STR:
            from_name = REAL_CASH
            op_type = FundOpTypeEnum.purchase
            target_name = YEB_NAME
        else:
            raise NotSupportError(f'暂时无法处理交易行为：{comment_str}, tail_comt:{tail_comt}')
        return op_type, from_name, target_name

    def _deal_complex_prod(self, comment_str: str) -> tuple:
        """
        有的商品名比较复杂，如：易方达黄金主题(QDII-LOF-FOF)A ，导致分割出错
        :param comment_str:
        :return:
        """
        comment_list = comment_str.split('-')
        _, *mid_comt_split_list, tail_comt = comment_list
        if tail_comt == ANT_FORTUNE_SALE_TO_YEB:
            op_type = FundOpTypeEnum.sale
            # 易方达黄金主题(QDII-LOF-FOF)A
            from_name = '-'.join(mid_comt_split_list)
            target_name = YEB_NAME
            return op_type, from_name, target_name
        elif tail_comt == ANT_FORTUNE_PURCHASE_STR:
            # 易方达黄金主题(QDII-LOF-FOF)A
            from_name = YEB_NAME
            op_type = FundOpTypeEnum.purchase
            target_name = '-'.join(mid_comt_split_list)
            return op_type, from_name, target_name
        else:
            raise NotSupportError(f'暂时无法处理交易行为：{comment_str}')

    def _deal_single_comment(self, comment_str: str) -> tuple:
        comment_list = comment_str.split('-')
        prod = comment_list[0]
        if prod == ANT_FORTUNE_HB_REWARD_PURCHASE_STR:
            from_name = f'<{HB_NAME}>'
            op_type = FundOpTypeEnum.purchase
            target_name = YEB_NAME
        elif prod == ANT_FORTUNE_RECEIVED_TO_YEB:
            from_name = REAL_CASH
            op_type = FundOpTypeEnum.purchase
            target_name = YEB_NAME
        elif prod == ANT_FORTUNE_YEB_YE_TO_YLB:
            from_name = REAL_CASH
            op_type = FundOpTypeEnum.sale
            target_name = YLB_NAME
        else:
            raise NotSupportError(f'暂时无法处理交易行为：{comment_str}')
        return op_type, from_name, target_name

    def analysis_operate(self, comment_str: str) -> tuple:
        """
        分割说明文字，解析交易行为
        FIXME: PY3.10 match-case
        """
        op_type, from_name, target_name = None, None, None
        comment_list = comment_str.split('-')
        if comment_str:
            comt_len = len(comment_list)
            if comt_len == 1:
                op_type, from_name, target_name = self._deal_single_comment(comment_str)
            elif comt_len == 2:
                op_type, from_name, target_name = self._deal_transfer(comment_str)
            elif comt_len == 3:
                op_type, from_name, target_name = self._deal_enum_operate(comment_str)
            elif comt_len == 4:
                '''
                卖出退款，此时我们对重新买入产品不感兴趣
                '''
                _, from_name, raw_to_name, transfer_status = comment_list
                op_type = FundOpTypeEnum.transfer_refund
                target_name = YEB_NAME
            elif comt_len == 5:
                op_type, from_name, target_name = self._deal_complex_prod(comment_str)
            else:
                raise NotSupportError(f'暂时无法处理交易行为：{comment_str}')
        return op_type, from_name, target_name

    def change_to_user_friendly(self, comment: str):
        """
        根据comment转换为用户可读的内容
        :param comment:
        :return:
        """
        op_type = self.analysis_operate(comment)[0]
        if op_type:
            op_desc = op_type.label
            op_name = op_type.name
            op_input = USER_INPUT_EXCEL_DICT.get(op_name, op_desc)
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

    def parse_comment(self, invest_df: PdDataFrame) -> PdDataFrame:
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

        invest_df_cp['op_type'] = invest_df_cp.comment.map(lambda x: self.change_to_user_friendly(x).get('name'))
        invest_df_cp['op_type_read'] = invest_df_cp.comment.map(lambda x: self.change_to_user_friendly(x).get('input'))
        invest_df_cp['op_type_desc'] = invest_df_cp.comment.map(lambda x: self.change_to_user_friendly(x).get('desc'))

        invest_df_cp['from_prod'] = invest_df_cp.comment.map(lambda x: self.analysis_operate(x)[1])
        invest_df_cp['to_prod'] = invest_df_cp.comment.map(lambda x: self.analysis_operate(x)[2])
        return invest_df_cp


class PCTransfer(ALiPayTransfer):
    """
    网页端导出账单使用该类
    """

    def __init__(self,
                 start_data_header=4,
                 source_fp: Union[str, Path] = PC_ALIPAY_RECORDS_FP,
                 drop_tail_line_index: int = 7,
                 base_export_file_name=BASE_PC_FILE_EXPORT_NAME,
                 drop_columns=None,
                 last_columns_str=PC_LAST_COLUMNS_STR,
                 output_columns=None):

        # super().__init__(self)
        if output_columns is None:
            output_columns = PC_OUTPUT_COLUMNS
        if not drop_columns:
            drop_columns = PC_DROP_COLUMNS
        self.start_data_header = start_data_header
        self.source_fp = source_fp
        self.drop_tail_line_index = drop_tail_line_index
        self.drop_columns = drop_columns
        self.base_export_file_name = base_export_file_name
        self.output_columns = output_columns
        self.last_columns_str = last_columns_str

    def get_datetime_dict(self, fp: Union[str, Path], date_line: int = 2) -> Optional[Dict]:
        """ 获取账单起止日期"""
        datetime_text = ''
        with open(fp, 'r', encoding=ENCODING) as csv_file:
            data = csv.reader(csv_file)
            #     print(data)
            line = 0
            for row in data:
                if line == date_line:
                    datetime_text = row[0]
                line += 1
        if datetime_text:
            # 起始时间：[2021-01-01 00:00:00]    终止时间：[2021-12-31 23:59:59]
            date_dict = self.get_durations(datetime_text)
            return date_dict

    def main(self):
        raw_df = self.get_raw_df(self.source_fp, header=self.start_data_header)
        renamed_df = self.pre_prepared_df(raw_df, self.last_columns_str)
        date_dict = self.get_datetime_dict(self.source_fp)
        prefix = f'起始时间[{date_dict.get("start_datetime")}]-终止时间[{date_dict.get("end_datetime")}]'
        # 去掉尾部注释性文字（包含用户隐私数据）
        useful_df = self.df_drop_useless_tail(renamed_df, drop_tail_line_index=self.drop_tail_line_index)
        # 去掉数据中的冗余whitespace
        invest_df = self.strip_df_values(useful_df)

        analysis_df = self.parse_comment(invest_df)
        # 根据用户意愿删除流水号
        if not IS_RECORD_TRANSACTIONAL_NUMBER:
            analysis_df.drop(columns='trans_code', inplace=True)
        else:
            analysis_df['trans_code'] = analysis_df.trans_code.apply(lambda x: x + '\t')
        # 删除无用字段
        analysis_df.drop(columns=self.drop_columns, inplace=True)

        with_date_name = f'{prefix}-{self.base_export_file_name}'
        alipay_export_fp = Path(current_path).joinpath(with_date_name)
        analysis_df.rename(columns=self.output_columns, inplace=True)

        analysis_df.to_csv(alipay_export_fp, index=False)
        print(f'结果已保存到：{alipay_export_fp}')
        return 0


class MobileTransfer(ALiPayTransfer):
    """
    移动端导出账单使用该类
    """

    def __init__(self,
                 start_data_header=1,
                 source_fp: Union[str, Path] = MOBILE_ALIPAY_RECORDS_FP,
                 drop_tail_line_index: int = 20,
                 base_export_file_name: str = BASE_PC_FILE_EXPORT_NAME,
                 last_columns_str: str = MB_LAST_COLUMNS_STR,
                 drop_columns: List = None,
                 output_columns: List = None):
        super().__init__()
        if output_columns is None:
            output_columns = MB_OUTPUT_COLUMNS
        if not drop_columns:
            drop_columns = MOBILE_DROP_COLUMNS
        super().__init__()
        self.start_data_header = start_data_header
        self.source_fp = source_fp
        self.drop_tail_line_index = drop_tail_line_index
        self.drop_columns = drop_columns
        self.base_export_file_name = base_export_file_name
        self.output_columns = output_columns
        self.last_columns_str = last_columns_str

    def operate_fund(self, invest_df: PdDataFrame) -> PdDataFrame:
        """
        筛选其中赎购基金的操作
        :param invest_df:
        :return:
        """
        invest_df = invest_df.loc[invest_df['comment'].str.contains(ANT_FORTUNE_STR)]
        return invest_df

    def filter_invest_df(self, renamed_df: PdDataFrame) -> PdDataFrame:
        """
        过滤出所有包含"投资理财"行为的交易数据
        :param renamed_df:
        :return:
        """
        not_null_df = renamed_df[~renamed_df.trans_type.isnull()]
        invest_df = not_null_df[not_null_df.trans_type == FILTER_INVEST_DATA_STR]
        return invest_df

    def get_code_from_comment(self):
        """
        解析comment，获取交易的基金，从而调用接口获取交易的基金编码
        :return:
        """
        pass

    def get_datetime_dict(self, dt: PdDataFrame) -> Optional[Dict]:
        """ 获取账单起止日期"""
        # 起始时间：[2021-01-01 00:00:00]    终止时间：[2021-12-31 23:59:59]
        datetime_text = dt.iloc[-16:-15]['op_type'].to_list()[0]
        date_dict = self.get_durations(datetime_text)
        return date_dict

    def main(self):
        """
        :return:
        """
        raw_df = self.get_raw_df(self.source_fp, header=self.start_data_header)

        renamed_df = self.pre_prepared_df(raw_df, self.last_columns_str)
        date_dict = self.get_datetime_dict(renamed_df)
        prefix = f'起始时间[{date_dict.get("start_datetime")}]-终止时间[{date_dict.get("end_datetime")}]'
        # 去掉尾部注释性文字（包含用户隐私数据）
        useful_df = self.df_drop_useless_tail(renamed_df, drop_tail_line_index=20)
        # 只保留基金交易数据
        striped_df = self.strip_df_values(useful_df)
        invest_df = self.filter_invest_df(striped_df)

        analysis_df = self.parse_comment(invest_df)
        # 根据用户意愿删除流水号
        if not IS_RECORD_TRANSACTIONAL_NUMBER:
            analysis_df.drop(columns='trans_code', inplace=True)
        else:
            analysis_df['trans_code'] = analysis_df.trans_code.apply(lambda x: x + '\t')
        # 删除无用字段
        analysis_df.drop(columns=self.drop_columns, inplace=True)

        with_date_name = f'{prefix}-{self.base_export_file_name}'
        alipay_export_fp = Path(current_path).joinpath(with_date_name)
        analysis_df.rename(columns=self.output_columns, inplace=True)

        analysis_df.to_csv(alipay_export_fp, index=False)
        print(f'结果已保存到：{alipay_export_fp}')
        return 0


if __name__ == '__main__':
    # mb = MobileTransfer()
    # ret = mb.main()
    pc = PCTransfer()
    result = pc.main()
    print(result)

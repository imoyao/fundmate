#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/7/23 14:00
"""
基金账本相关
TODO: 用户账户和基金账户容易混淆，可能使用嵌套蓝图更好
"""
import datetime
from pathlib import Path
from typing import Optional, Union

from apiflask import APIBlueprint, input, output
from flask.views import MethodView
from flask_praetorian import auth_required, current_user

import pandas as pd

from backend.fundmate import errors, excepts, utils
from backend.fundmate.account.deal_trades import ImportColumns, ImportTradeEnum
from backend.fundmate.account.models import Account, AccountTransactionRecord
from backend.fundmate.account.schemas import AccountOutSchema, CreateAccountSchema
from backend.fundmate.data.eastmoney.trade_day import TradeDay
from backend.fundmate.fund.models import Fund, InvestProduct
from backend.fundmate.libs import convert
from backend.fundmate.settings import FundOpTypeEnum, SupportInvestCategoriesEnum
from backend.fundmate.types import PdDataFrame

bp = APIBlueprint("account", __name__, url_prefix="/accounts")


@bp.route('/<int:account_id>')
class AccountsDetail(MethodView):
    """
    获取指定账户的信息
    """

    @output(AccountOutSchema)
    def get(self, account_id: str):
        """查询某个账本基本信息
        名称、描述、包含的基金、比例、金额
        """
        account_inst = Account.get_by_id(account_id)
        return account_inst

    @input(CreateAccountSchema(partial=True))
    @output(AccountOutSchema)
    def patch(self, pet_id, data):
        """更新账户信息
        名称，描述，
        """
        pass


# TODO: 逻辑层分离到单独模块
def read_csv_for_df(fp: Union[str, Path], has_transfer: bool = False) -> Optional[PdDataFrame]:
    """
    读取用户上传的csv，获取文件需要处理的数据集
    :param has_transfer: 是否包含转换操作
    :param fp:
    :return:
    """
    df = pd.read_csv(fp)
    df_columns = df.columns.to_list()
    if has_transfer:
        if ImportTradeEnum.trade_out_prod.label not in df_columns:
            raise excepts.NotSupportError('包含基金“转换”操作时必须包含“赎回产品”列！')

    trade = ImportTradeEnum()
    optional_columns = trade.optional_labels
    BASE_COLUMNS = trade.required_labels
    _df_head_cp = BASE_COLUMNS.copy()
    if set(BASE_COLUMNS).issubset(set(df_columns)):
        for optional_item in optional_columns:
            if optional_item in df_columns:
                _df_head_cp.append(optional_item)
        useful_df = df[_df_head_cp]
        return useful_df
    else:
        return None


def check_isvalid_trade_types(types: Optional[list] = None) -> bool:
    """
    检查所有的交易行为都支持
    :return:
    """
    all_types = FundOpTypeEnum.display()
    return set(types).issubset(set(all_types))


def check_isvalid_prods(platform: str, prods: Optional[list] = None) -> bool:
    """
    检查用户所购买产品是否都支持导入操作
    :return:
    """
    type_repr = ImportTradeEnum.trade_category.dk_value
    code_repr = ImportTradeEnum.redeem_prod.dk_value

    p_types = [item.get(type_repr) for item in prods]
    all_types = SupportInvestCategoriesEnum.input()
    s_in_types = set(p_types)
    s_all_types = set(all_types)
    if not s_in_types.issubset(s_all_types):
        not_in_types = s_in_types - s_all_types
        msg = ','.join(not_in_types)
        raise excepts.NotSupportError(f'不支持的交易品类：{msg}')
    for p_item in prods:
        code = p_item.get(code_repr)
        p_type = p_item.get(type_repr)
        if p_type == SupportInvestCategoriesEnum.fund.dk_value:
            f = Fund.filter_by_code(code)
            if not f:
                raise excepts.NotSupportError(f'不支持的基金编码：{code}')
        elif p_type == SupportInvestCategoriesEnum.financial_product.dk_value:
            prod = InvestProduct.filter_by_plt_code(platform, code)
            if not prod:
                # 只要有一个不满足，则break
                raise excepts.NotSupportError(f'不支持的理财产品编码：{code}')
        else:
            raise excepts.NotSupportError('目前仅支持导入基金和部分理财产品！')
    return True


def dumps_template():
    """
    从数据中读取内容，导出为文件
    :return:
    """
    pass


def loads_template(df: PdDataFrame):
    """
    转换模板文件，保存到数据库中
    1. 交易类型中文转代码
    2. 产品编码转系统编码
    3. 交易日期和确认日期确定
    :return:
    """

    def _deal_op_type(op_type_cn: str) -> str:
        """
        将用户输入的汉字转为程序
        :param op_type_cn: 
        :return:
        """
        name_label_maps = FundOpTypeEnum.columns_map()
        reverse_name_label_maps = utils.key2val(name_label_maps)
        repr_name = reverse_name_label_maps.get(op_type_cn)
        return repr_name

    def _db_code(trade_category: str, prod_code: str) -> str:
        """
        产品最终保存到流水记录表时的编码
        :param trade_category:
        :param prod_code:
        :return:
        """
        if trade_category in [
                SupportInvestCategoriesEnum.fund.dk_value,
                # SupportInvestCategoriesEnum.stock.dk_value,
                # SupportInvestCategoriesEnum.bond.dk_value
        ]:
            return prod_code
        # 理财产品
        elif trade_category == SupportInvestCategoriesEnum.financial_product.dk_value:
            _inst = InvestProduct.filter_by_plt_code(trade_category, prod_code)
            return _inst.prod_code
        else:
            raise excepts.NotSupportError('目前仅支持导入基金和部分理财产品！')

    def fetch_confirm_datetime(fund_code: str, operate_date: str, op_type: str, trade_category: str):
        """获取购买基金的确认日期"""
        temp_datetime = convert.try_parse_date(operate_date)
        date_str = temp_datetime.strftime("%Y-%m-%d")
        if trade_category in [SupportInvestCategoriesEnum.fund.dk_value, SupportInvestCategoriesEnum.fund.dk_value]:
            td = TradeDay()
            is_after_15o_clock = temp_datetime.hour >= 15
            is_buy = op_type == FundOpTypeEnum.purchase
            if trade_category == SupportInvestCategoriesEnum.fund.dk_value:
                ret = td.get_trade_info(fund_code, date_str, is_buy=is_buy, is_after_15o_clock=is_after_15o_clock)
                return ret.get('deadline')
            elif trade_category == SupportInvestCategoriesEnum.financial_product.dk_value:
                # 理财产品，直接按照t+1的基金产品计算
                ret = td.get_trade_info('163406', date_str, is_buy=is_buy, is_after_15o_clock=is_after_15o_clock)
                return ret.get('maturity')
            else:
                return date_str

    # 注意顺序不可调整
    if 'trade_repr' in df.columns:
        df.drop(columns='op_type', inplace=True)
        df.rename({'trade_repr': 'op_type'}, inplace=True)
    else:
        df['op_type'] = df.op_type.apply(lambda x: _deal_op_type(x))

    df['purchase_prod'] = df.apply(lambda row: _db_code(row['trade_category'], row['purchase_prod']), axis=1)
    df['redeem_prod'] = df.apply(lambda row: _db_code(row['trade_category'], row['redeem_prod']), axis=1)
    # 交易确定日
    df['trans_confirm_date'] = df.apply(lambda row: fetch_confirm_datetime(
        row['redeem_prod'],
        row['launch_trans_date'],
        row['trade_category'],
        row['op_type'],
    ),
                                        axis=1)
    # 交易手续费：如果不是0，则返回，否则，根据购买金额，购买基金、费率计算
    df['charge_fee'] = df.apply(lambda row: _db_code(row['record_code'], row['trans_confirm_date']), axis=1)


class ImportDealingDocuments(MethodView):

    @auth_required
    @output(AccountOutSchema)
    def post(self, data: dict):
        """
        通过文件导入账单
        """
        upload_file = data.get('file')
        platform = data.get('platform')
        # 包含基金转换操作，如果是，则需要from，to字段
        has_transfer = data.get('has_transfer')
        is_csv = utils.check_is_csv(upload_file)
        if not is_csv:
            raise errors.NotExceptedFileError
        else:
            try:
                upload_file_df = read_csv_for_df(upload_file, has_transfer=has_transfer)
            except excepts.NotSupportError as e:
                msg = str(e)
                raise errors.NotSupportProduct(message=msg)

            t = ImportColumns()
            if upload_file_df is not None:
                rename_dict = FundOpTypeEnum.columns_map()
                repr_df = upload_file_df.rename(columns=rename_dict)

                # TODO: 需要产品编码和产品品类（基金，理财产品、股票、转债、投顾组合等）

                # FIXME:需要对赎回和申购的产品都进行拼接（set）
                filter_subset = [ImportTradeEnum.redeem_prod.dk_value, ImportTradeEnum.trade_category.dk_value]
                filter_subset_df = repr_df.drop_duplicates(subset=filter_subset, keep='first')
                # 去重结果转list
                prod_codes = filter_subset_df[filter_subset].to_dict(orient='records')

                trade_types = repr_df.trade_type.unique().to_list()
                # 1. 检查数据完整度（包括交易行为、交易产品）
                isvalid_types = check_isvalid_trade_types(trade_types)
                try:
                    isvalid_prods = check_isvalid_prods(platform, prod_codes)
                except excepts.NotSupportError as e:
                    msg = str(e)
                    raise errors.NotSupportProduct(message=msg)

                all_isvalid = all([isvalid_types, isvalid_prods])
                if all_isvalid:
                    '''
                    # 2. 读取文件并导入

                    '''
                    user = current_user()
                    user_id = user.id
                    all_in_names = t.required_names + t.optional_names
                    all_db_names = AccountTransactionRecord.__table__.columns
                    dumps_dict = {
                        'trade_type': 'op_type',
                        'redeem_prod': 'redeem_prod',
                        'purchase_prod': 'purchase_prod',
                        'trade_amount': 'amount',
                        'trade_datetime': 'launch_trans_date',
                        'trade_comment': 'plat_comment',
                        'trade_record': 'record_code',
                        'trade_fee': 'charge_fee',
                    }
                    is_in_ok = set(dumps_dict.keys()).issubset(set(all_in_names))

                    dumps_df = repr_df.rename(columns=rename_dict)
                    # 2.1 操作者信息添加user_id列
                    dumps_df['user_id'] = user_id
                    dumps_df['create_at'] = datetime.datetime.now()
                    db_columns = dumps_df.columns.to_list()
                    is_to_db_ok = set(db_columns).issubset(set(all_db_names))
                    # 导入前最后的文件头检查
                    if not all([is_in_ok, is_to_db_ok]):
                        raise errors.TransactionRecordError
                    else:
                        loads_template(dumps_df)
                else:
                    if not isvalid_types:
                        raise errors.NotSupportInvestType
                    else:
                        raise errors.NotSupportProduct

            else:
                required_labs = t.required_labels
                raise errors.NotExceptedFileError(message=f'账单导入上传文件必须包含字段：{required_labs}')

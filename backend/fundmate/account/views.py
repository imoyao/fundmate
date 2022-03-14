#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/7/23 14:00
"""
基金账本相关
TODO: 用户账户和基金账户容易混淆，可能使用嵌套蓝图更好
"""
import datetime

from apiflask import APIBlueprint, input, output
from flask.views import MethodView
from flask_praetorian import auth_required, current_user

from backend.fundmate import errors, excepts, utils
from backend.fundmate.account.deal_trades import ImportColumns, ImportTradeEnum
from backend.fundmate.account.models import Account, AccountTransactionRecord
from backend.fundmate.account.schemas import AccountOutSchema, CreateAccountSchema
from backend.fundmate.fund.load_templates import (
    check_isvalid_prods,
    check_isvalid_trade_types,
    loads_template,
    read_csv_for_df,
)

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
                rename_dict = ImportTradeEnum.columns_map()
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

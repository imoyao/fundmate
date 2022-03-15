#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/2/15 10:51
@file: deal_trades.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 用于处理交易账单的中间件
"""
import enum

from backend.fundmate.libs.dk_enums import BaseTypeEnum, ChoiceTypeDk

TRADE_TYPE = ChoiceTypeDk('trade_type', '交易类型')
TRADE_CATEGORY = ChoiceTypeDk('trade_category', '交易品类')  # 基金/股票？详见 SupportInvestCategoriesEnum
PURCHASE_PROD = ChoiceTypeDk('purchase_prod', '购入产品')  # 代码
REDEEM_PROD = ChoiceTypeDk('redeem_prod', '赎回产品')  # 代码
TRADE_AMOUNT = ChoiceTypeDk('trade_amount', '交易金额')
TRADE_DATETIME = ChoiceTypeDk('trade_datetime', '交易时间')
TRADE_COMMENT = ChoiceTypeDk('trade_comment', '商品说明')
TRADE_RECORD = ChoiceTypeDk('trade_record', '渠道交易流水号')
TRADE_FEE = ChoiceTypeDk('trade_fee', '交易手续费')
TRADE_REPR = ChoiceTypeDk('trade_repr', '程序描述标识')


@enum.unique
class ImportTradeEnum(BaseTypeEnum):
    trade_type = TRADE_TYPE
    trade_category = TRADE_CATEGORY
    purchase_prod = PURCHASE_PROD
    redeem_prod = REDEEM_PROD
    trade_amount = TRADE_AMOUNT
    trade_datetime = TRADE_DATETIME
    trade_comment = TRADE_COMMENT
    trade_record = TRADE_RECORD
    trade_fee = TRADE_FEE
    trade_repr = TRADE_REPR

    @classmethod
    def input(cls) -> list:
        """
        用户请求时需要用到
        :return:
        """
        return [item.dk_value for item in cls]

    @classmethod
    def columns_map(cls) -> dict:
        """
        {'交易类型': 'trade_type', '交易产品': 'trade_prod', '交易金额': 'trade_amount', '交易时间': 'trade_datetime',
        '商品说明': 'trade_comment', '渠道交易流水号': 'trade_record', '交易手续费': 'trade_fee'}

        :return:
        """
        cols_maps = dict(zip(cls.labels(), cls.input()))
        return cols_maps


class ImportColumns:

    @property
    def required(self):
        _cols = [
            ImportTradeEnum.trade_type, ImportTradeEnum.purchase_prod, ImportTradeEnum.trade_amount,
            ImportTradeEnum.trade_datetime, ImportTradeEnum.trade_category
        ]
        return _cols

    @property
    def options(self):
        _cols = [
            ImportTradeEnum.trade_comment, ImportTradeEnum.trade_record, ImportTradeEnum.trade_fee,
            ImportTradeEnum.redeem_prod, ImportTradeEnum.trade_repr
        ]
        return _cols

    @property
    def required_labels(self) -> list:
        _cols = self.required
        return [item.label for item in _cols]

    @property
    def required_names(self) -> list:
        _cols = self.required
        return [item.dk_value for item in _cols]

    @property
    def optional_labels(self) -> list:
        _cols = self.options
        return [item.label for item in _cols]

    @property
    def optional_names(self) -> list:
        _cols = self.options
        return [item.dk_value for item in _cols]


itr = ImportColumns()

if __name__ == '__main__':
    col_names = itr.required_names
    col_labels = itr.optional_labels
    cols = ImportTradeEnum.columns_map()
    a = ImportTradeEnum.input()

    print(col_names, col_labels, cols, a)

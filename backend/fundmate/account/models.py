#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/2/13 18:12
from typing import Union

from backend.fundmate.compat import basestring
from backend.fundmate.database import (
    Base,
    ChoiceTypeInteger,
    Column,
    CreateDateModel,
    PkModel,
    db,
    key2val,
    reference_col,
)
from backend.fundmate.settings import RISK_TYPE


class Account(Base, PkModel, CreateDateModel):
    """
    账本类型有两个维度：
    1. 四笔钱（风险纬度）
    2. 投资产品（股票、基金、银行理财、现金）
    """
    __table_args__ = {'comment': '账本（钱包）'}

    name = Column(db.String(255), comment='账本名称')
    creator_id = reference_col('users', column_kwargs={'comment': '管理人（类似群主）'})
    comment = Column(db.String(255), comment='账本备注')
    account_type = Column(ChoiceTypeInteger(choices=key2val(RISK_TYPE)), nullable=True, default=0, comment='账本类型（四笔钱）')

    @classmethod
    def get_by_id(cls, account_id: Union[str, int]):
        """根据账户编号获取信息"""
        if any((
                isinstance(account_id, basestring) and account_id.isdigit(),
                isinstance(account_id, int),
        )):
            return cls.query.get_or_404(int(account_id))
        return None


class AccountFund(Base, PkModel):
    fund_id = reference_col('funds', column_kwargs={'comment': '基金编号'})
    account_id = Column(db.Integer, comment='账本编号')


FUND_OP_TYPE = {
    'purchase': 1,  # 买入/存入/申购
    'sale': 2,  # 赎回/卖出/支取
    'transfer': 3,  # 转换/转存
    'regular_invest': 4,  # 定投
    'bonus': 5,  # 分红
    'adjust': 6,  # 调仓
    'other': 7,  # 其他
}


class CashFlow(Base, PkModel):
    """
    记账操作表 # TODO:或许命名为 TransactionRecord 更好
    """
    __table_args__ = {'comment': '操作记录表'}

    user_id = reference_col('users', column_kwargs={'comment': '购买用户编号'})
    op_type = Column(ChoiceTypeInteger(choices=key2val(FUND_OP_TYPE)), default=1, nullable=True, comment='操作类型')
    fund_id = reference_col('funds', column_kwargs={'comment': '所购买的基金编号'})
    amount = Column(db.Integer, comment='购买金额')
    date = Column(db.TIMESTAMP, nullable=False, server_default=db.text("CURRENT_TIMESTAMP"), comment='购买日期（确认日期）')
    comment = Column(db.String(300), comment='复盘备注')


class HandPick(Base, PkModel):
    __table_args__ = {'comment': '自选基金'}
    user_id = reference_col('users', column_kwargs={'comment': '用户编号'})
    fund_id = reference_col('funds', column_kwargs={'comment': '基金编号'})
    pick_time = Column(db.TIMESTAMP,
                       nullable=False,
                       server_default=db.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                       comment='收藏时间（用于计算加入自选以来收益）')
    comment = Column(db.String(300), comment='自选备注')  # TODO: 或许tag更合适

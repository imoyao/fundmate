#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/2/13 18:12

from backend.fundmate.database import Base, Column, CreateDateModel, PkModel, db, reference_col, DeclEnum

from backend.fundmate.fund.models import RiskType


class Account(Base, PkModel, CreateDateModel):
    __table_args__ = {'comment': '账本（钱包）'}

    name = Column(db.String(255), comment='账本名称')
    creator_id = reference_col('users', column_kwargs={'comment': '管理人（类似群主）'})
    comment = Column(db.String(255), comment='账本备注')
    account_type = Column(RiskType.db_type(), comment='账本类型（四笔钱）')


class AccountFund(PkModel):
    fund_id = reference_col('funds', column_kwargs={'comment': '基金编号'})
    account_id = Column(db.Integer, comment='账本编号')


class FundOpType(DeclEnum):
    """交易操作类型，参考支付宝与投资账本实现"""
    hold_in = 1, '买入/存入/申购'
    sale = 2, '赎回/卖出/支取'
    transfer = 3, '转换/转存'
    regular_invest = 4, '定投'
    bonus = 5, '分红'
    adjust = 6, '调仓'
    other = 7, '其他'


class CashFlow(Base, PkModel):
    """
    记账操作
    参考：
    1. “好买[基金账本 - 好买基金研究中心](https://www.howbuy.com/myfund/index.htm)”
    2. “同花顺投资账本”
    """
    user_id = reference_col('users', column_kwargs={'comment': '购买用户编号'})
    fund_id = reference_col('funds', column_kwargs={'comment': '所购买的基金编号'})
    amount = Column(db.Integer, comment='购买金额')
    date = Column(db.TIMESTAMP,
                  nullable=False,
                  server_default=db.text("CURRENT_TIMESTAMP"),
                  comment='购买日期（确认日期）')
    comment = Column(db.String(300), comment='复盘备注')
    op_type = Column(FundOpType.db_type(), comment='操作类型')


class HandPick(Base, PkModel):
    __table_args__ = {'comment': '自选基金'}
    user_id = reference_col('users', column_kwargs={'comment': '用户编号'})
    fund_id = reference_col('funds', column_kwargs={'comment': '基金编号'})
    pick_time = Column(db.TIMESTAMP,
                       nullable=False,
                       server_default=db.text(
                           "CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                       comment='收藏时间（用于计算加入自选以来收益）')
    comment = Column(db.String(300), comment='自选备注')  # TODO: 或许tag更合适

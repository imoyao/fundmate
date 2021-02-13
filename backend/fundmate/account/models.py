#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Administrator at 2021/2/13 18:12

from backend.fundmate.database import Column, CreateDateModel, PkModel, db


class Account(PkModel, CreateDateModel):
    __table_args__ = {'comment': '账本（钱包）'}

    name = Column(db.String(255), comment='账本名称')
    creator_id = Column(db.Integer, comment='管理人（群主）')
    comment = Column(db.String(255), comment='账本备注')


class AccountFund(PkModel):
    fund_id = Column(db.Integer, comment='基金编号')
    account_id = Column(db.Integer, comment='账本编号')


class CashFlow(PkModel):
    uid = Column(db.Integer, comment='购买用户')
    fid = Column(db.Integer, comment='所购买的基金')
    amount = Column(db.Integer, comment='购买金额')
    date = Column(db.TIMESTAMP,
                  nullable=False,
                  server_default=db.text("CURRENT_TIMESTAMP"),
                  comment='购买日期（确认日期）')
    comment = Column(db.String(30), comment='复盘备注')


class HandPick(PkModel):
    __table_args__ = {'comment': '自选基金'}

    uid = Column(db.Integer, comment='用户编号')
    fid = Column(db.Integer, comment='基金编号')
    pick_time = Column(db.TIMESTAMP,
                       nullable=False,
                       server_default=db.text(
                           "CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                       comment='收藏时间')
    comment = Column(db.String(30), comment='备注')

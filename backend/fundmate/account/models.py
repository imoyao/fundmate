#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/2/13 18:12
from typing import Optional, Union

from backend.fundmate import settings
from backend.fundmate.compat import basestring
from backend.fundmate.database import (
    Column,
    CreateDateModel,
    IntChoiceDkEnumType,
    PkModel,
    UpsertMixin,
    db,
    gen_digit_code,
    reference_col,
)


class Account(PkModel, CreateDateModel, UpsertMixin):
    """
    账本类型有两个维度：
    1. 四笔钱（风险纬度）
    2. 投资产品（股票、基金、银行理财、现金）
    """
    __table_args__ = {'comment': '账本（钱包）'}

    account_code = Column(db.String(10), comment='组合编码')  # 使用固定数字加随机数
    name = Column(db.String(10), comment='账本名称')
    creator_id = reference_col('users', column_kwargs={'comment': '管理人（类似群主）'})
    desc = Column(db.String(300), comment='账本备注')
    rich_desc = Column(db.String(1000), comment='账本详细描述')
    account_type = Column(IntChoiceDkEnumType(settings.RiskTypeEnum,
                                              default=settings.RiskTypeEnum.default().dk_value,
                                              impl=db.Integer()),
                          nullable=True,
                          comment=f'账本类型（四笔钱）：{settings.RiskTypeEnum.comment()}')

    @classmethod
    def get_by_id(cls, account_id: Union[str, int]):
        """根据账户编号获取信息"""
        if any((
                isinstance(account_id, basestring) and account_id.isdigit(),
                isinstance(account_id, int),
        )):
            return cls.query.get_or_404(int(account_id))
        return None

    @classmethod
    def gen_account_code(cls) -> Optional[str]:
        """
        生成递增6位组合识别号
        :return:
        """
        fp_identifier = gen_digit_code(cls.account_code, settings.INITIAL_ACCOUNT_IDENTIFIER, min_len=4)
        return fp_identifier


# class AccountFund(PkModel):
#     fund_id = reference_col('funds', column_kwargs={'comment': '基金编号'})
#     account_id = Column(db.Integer, comment='账本编号')


class AccountTransactionRecord(PkModel, CreateDateModel, UpsertMixin):
    """
    记账操作表
    """
    __table_args__ = {'comment': '操作记录表'}

    user_id = reference_col('users', column_kwargs={'comment': '购买用户编号'})
    op_type = Column(IntChoiceDkEnumType(settings.FundOpTypeEnum,
                                         default=settings.FundOpTypeEnum.default().dk_value,
                                         impl=db.Integer()),
                     comment=f'操作类型：{settings.FundOpTypeEnum.comment()}')
    fund_code = Column(db.String(6), comment='所购买的基金编号')
    amount = Column(db.Numeric(32, 4), comment='购买金额')
    charge_fee = Column(db.Numeric(32, 4), comment='操作手续费，如：123456.0716')
    launch_trans_date = Column(db.DateTime, nullable=True, comment='交易发起日期')
    trans_confirm_date = Column(db.Date, nullable=False, comment='交易确认日期')
    transaction_id = Column(db.BigInteger, comment='调仓历史编码')  # 使用雪花算法
    update_time = Column(db.DateTime, comment='数据更新时间')
    comment = Column(db.String(300), comment='复盘备注')


class HandPick(PkModel):
    __table_args__ = {'comment': '自选基金'}
    user_id = reference_col('users', column_kwargs={'comment': '用户编号'})
    fund_code = Column(db.String(6), comment='所购买的基金编号')
    pick_time = Column(db.TIMESTAMP,
                       nullable=False,
                       server_default=db.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                       comment='收藏时间（用于计算加入自选以来收益）')
    comment = Column(db.String(300), comment='自选备注')  # TODO: 或许tag更合适

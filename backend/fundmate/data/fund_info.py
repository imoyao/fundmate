#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/3/9 15:44
@file: fund_info.py
@author: imoyao
@email: immoyao@gmail.com
@desc:基金信息更新
"""
from typing import Dict

from sqlalchemy import func

from backend.fundmate.data.danjuan.base import FundInfo
from backend.fundmate.data.eastmoney.base import EastMoney
from backend.fundmate.data.ten_jqka.base import FundInfo as AiFundInfo
from backend.fundmate.database import db
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import Fund

em = EastMoney()
djf = FundInfo()
ai_fund = AiFundInfo()


def update_fund_info(fund_code: str) -> Dict:
    """
    更新指定基金的信息
    目前只更新full_name字段
    :param fund_code:
    :return:
    """
    fund_info = em.fund_base_info(fund_code)
    # 存数据库时删除冗余数据
    fund_info.pop('f_var_name')
    fund_info.pop('company')

    fund_inst = Fund.filter_by_code(fund_code)
    fund_inst.update(**fund_info)
    return fund_info


def init_fund(is_init: bool = False):
    """
    初始化或者更新基金信息
    :param is_init: 初始化会重新更新表
    :return:
    """
    fund_counts = db.session.query(func.count(Fund.id)).scalar()
    if fund_counts == 0:
        is_init = True
    if is_init:
        # 保存基本信息
        em.fund(save=True, format_='sql')

    fund_lists = Fund.query.with_entities(Fund.fund_code).filter(Fund.full_name.is_(None)).all()
    # fund_lists = Fund.query.with_entities(Fund.fund_code).all()
    for fund in fund_lists:
        fund_code = fund[0]
        update_fund_info(fund_code)
        logger.success(f'基金 {fund_code} 信息更新成功……')

    return 0

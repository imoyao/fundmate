#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/3/9 15:44
@file: fund_info.py
@author: imoyao
@email: immoyao@gmail.com
@desc:基金信息更新
"""
from sqlalchemy import func

from backend.fundmate.data.danjuan.base import FundInfo
from backend.fundmate.data.eastmoney.base import EastMoney
from backend.fundmate.database import db
from backend.fundmate.fund.models import Fund

em = EastMoney()
djf = FundInfo()


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
    for fund in fund_lists:
        fund_code = fund[0]
        fd_full_name = djf.fund_full_name(fund_code)
        if fd_full_name:
            fund_inst = Fund.filter_by_code(fund_code)
            name = fund_inst.name
            if name != fd_full_name:
                fund_inst.update(full_name=fd_full_name)
        else:
            continue
    return 0

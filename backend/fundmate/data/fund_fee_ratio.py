#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/8/18 16:46
"""
更新基金费率的脚本
1. 尝试基金决策宝
2. 对于基金决策宝更新失败的 TODO:尝试天天基金或者蛋卷基金？
"""
from typing import Union

from backend.fundmate.data.dkhs.base import jcb
from backend.fundmate.excepts import EmptyError, UnexpectedArgsError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import Fund


def init_fee_ratio(fund_code: Union[str, None] = None):
    """
    初始化或者更新费率信息（支持更新单个）
    :return:
    """
    if not fund_code:
        fund_lists = Fund.query.all()
        not_success_set = set()
        for fd in fund_lists:
            fund_code = fd.fund_code
            try:
                ret = jcb.fee_ratio(fund_code)
            except (UnexpectedArgsError, EmptyError) as e:
                logger.error(e)
                ret = None
            if ret is None:
                not_success_set.add(fund_code)
        if not_success_set:
            failed_counts = len(not_success_set)
            logger.warning(
                f'Hits:{failed_counts} of fund failed to update fee ratio while {len(fund_lists) - failed_counts} '
                f'success,they are:{not_success_set}')
    else:
        try:
            ret = jcb.fee_ratio(fund_code)
        except (UnexpectedArgsError, EmptyError):
            ret = None
        if ret is None:
            logger.warning(f'Failed to update fee ratio of {fund_code}.')


if __name__ == '__main__':
    init_fee_ratio()

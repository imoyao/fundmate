#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/3/11 16:23
@file: utils.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 返回产品名称、产品编码、产品类型对应关系
"""
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

import pandas as pd

from backend.fundmate import settings
from backend.fundmate.data.eastmoney.base import EastMoney
from backend.fundmate.fund.models import Fund

em = EastMoney()
current_path = Path(__file__).parent.resolve()

RESULT_FILE_NAME = '起始时间[20121201-000000]-终止时间[20220119-163035]-PC端支付宝交易单导出.csv'
OUTPUT_FILE_NAME = '产品编号映射表.csv'
RESULT_FP = Path(current_path).joinpath(RESULT_FILE_NAME)
OUTPUT_FP = Path(current_path).joinpath(OUTPUT_FILE_NAME)


def unique_prods(result_fp: Union[str, Path]):
    """
    用户购买产品去重
    :param result_fp:
    :return:
    """
    df = pd.read_csv(result_fp)
    redeem_prods = df['卖出产品'].unique()
    purchase_prods = df['买入产品'].unique()
    all_prods = set(purchase_prods.tolist() + redeem_prods.tolist())
    return all_prods


def try_match_fund(prod_name: str) -> Optional[Dict]:
    f = Fund.search_name(prod_name)
    if f and len(f) == 1:
        code = f[0].fund_code
    else:
        code = em.search_fund_by_name(prod_name)
    if code:
        prod_item = {'prod': prod_name, 'code': code, 'category': settings.SupportInvestCategoriesEnum.fund.dk_value}
        return prod_item


def match_code_and_category(prod_set: Set) -> List:
    """
    # FIXME: 多线程加速
    :param prod_set:
    :return:
    """
    _item = dict()
    all_items = []
    for prod_name in prod_set:
        _item = try_match_fund(prod_name)
        if not _item:
            # 理财产品/组合
            _item = {'prod': prod_name, 'code': None, 'category': None}

        all_items.append(_item)

    return all_items


def dump_map(result_fp: Union[str, Path] = RESULT_FP, output_fp: Union[str, Path] = OUTPUT_FP):
    prod_set = unique_prods(result_fp)
    all_items = match_code_and_category(prod_set)
    pcc_df = pd.DataFrame(all_items)
    pcc_df.to_csv(output_fp, index=False)
    return all_items


if __name__ == '__main__':
    dump_map(RESULT_FP, OUTPUT_FP)

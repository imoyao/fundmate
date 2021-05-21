#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/28 18:12
import time
import xalpha as xa
from sqlalchemy import create_engine
from backend.fundmate import settings

DB_URL = settings.SQLALCHEMY_DATABASE_URI
engine = create_engine(DB_URL)


def fund_info(fund_code: str, save: bool = False) -> dict:
    """
    获取基金信息
    :param fund_code:
    :param save:
    :return:
    """
    if save:
        io = {"save": True, "fetch": True, "form": "sql", "path": engine}
        xa.fundinfo(fund_code, **io)

    f_with_prefix = f'F{fund_code}'
    info = xa.get_rt(f_with_prefix)  # 单独获取当日数据
    return info


def main(fund_type: str = 'all') -> int:
    """
    获取所有基金信息
    all，hh，zq, zs, gp, qdii, fof 分别对应全部混合，债券，指数，股票型的全部基金列表
    :param fund_type:
    :return:
    """
    all_funds = xa.misc.get_fund_list(fund_type)
    # ? 这样会导致表数量明显增多，是否会影响性能？[MySQL 数据库表的数量很多会造成什么不良影响？ - SegmentFault 思否](https://segmentfault.com/q/1010000000523024)
    for fund in all_funds:
        ret = fund_info(fund, save=True)
        print(ret)
    return 0


# 可以用 xa.misc.get_fund_list(str), str 可以是 "hh", "zq", "zs", "gp", "qdii" 等，对应混合基金，债券基金，指数基金，股票基金和 qdii 基金等
if __name__ == '__main__':
    main()

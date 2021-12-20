#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/28 18:12
import traceback

import xalpha as xa
from sqlalchemy import create_engine

from backend.fundmate import settings
from backend.fundmate.exts.flask_loguru import logger

DB_URL = settings.SQLALCHEMY_DATABASE_URI
engine = create_engine(DB_URL)


def fund_info(fund_code: str, save: bool = False) -> dict:
    """
    获取基金信息
    :param fund_code: 基金编码，6位纯数字
    :param save: 是否保存到数据库
    :return:基金信息，{'name': '诺安中证100指数A', 'time': '2021-05-20', 'current': 2.065,
    'market': 'CN', 'currency': 'CNY', 'current_ext': None, 'status': '开放申购', 'type': '股票指数',
    'scale': '2.54亿元（2021-03-31）', 'manager': '梅律吾', 'company': '诺安基金', 'estimate': 2.043, 'estimate_time':
    '2021-05-21 15:00'}
    """
    if save:
        io = {"save": True, "fetch": True, "form": "sql", "path": engine}
        try:
            xa.fundinfo(fund_code, **io)
        except ValueError as e:
            logger.info(f'Fund Code:{fund_code},Error:{e}')
            logger.error(traceback.print_exc())

    f_with_prefix = f'F{fund_code}'
    info = None
    try:
        # 获取当日数据可能出错
        info = xa.get_rt(f_with_prefix)  # 单独获取当日数据
    except IndexError as e:
        logger.info(f'Fund Code:{f_with_prefix},Error:{e}')
        logger.error(traceback.print_exc())
    return info


def main(fund_type: str = 'all') -> int:
    """
    获取所有基金信息
    [请问是否有api 可以一次获得所有基金编码？ · Issue #95 · refraction-ray/xalpha](https://github.com/refraction-ray/xalpha/issues/95)
    all,hh,zq, zs, gp, qdii, fof 分别对应全部混合，债券，指数，股票型的全部基金列表
    注意上述接口不够全，最终数据校验可参考此页面：
    [基金公司一览表 _ 天天基金网](http://fund.eastmoney.com/company/default.html)

    :param fund_type:
    :return:
    """
    import time
    start_time = time.time()
    all_funds = xa.misc.get_fund_list(fund_type)
    # 这样会导致表数量明显增多，是否会影响性能？[MySQL 数据库表的数量很多会造成什么不良影响？ - SegmentFault 思否](https://segmentfault.com/q/1010000000523024)
    # [Have too many tables in a Mysql database can affect performance? - Server Fault](
    # https://serverfault.com/questions/83438/have-too-many-tables-in-a-mysql-database-can-affect-performance)
    for fund in all_funds:
        ret = fund_info(fund, save=True)
        print(ret)
    logger.info(f'It cost {time.time() - start_time} to update fund value DB.')
    return 0


# 可以用 xa.misc.get_fund_list(str), str 可以是 "hh", "zq", "zs", "gp", "qdii" 等，对应混合基金，债券基金，指数基金，股票基金和 qdii 基金等
if __name__ == '__main__':
    main()

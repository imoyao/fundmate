#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/6/7 17:47
"""
该接口似乎不准确？
"""
from contextlib import contextmanager
from datetime import timedelta
from typing import Union

import baostock as bs
import pandas as pd

from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.libs import convert
from backend.fundmate.utils import HiddenPrints


@contextmanager
def trade_days_gen(start_date: str, end_date: Union[str, None] = None):
    """
    用于历史交易日查询（包括当年）的生成器
    TODO:需要验证：[沪深证券交易所发布2020年全年休市安排-东方财富网](https://finance.eastmoney.com/a/201912201331291892.html)
    :param start_date:
    :param end_date:
    :return:
    """
    if not end_date:
        str_to_date = convert.try_parse_date(start_date)
        real_end_date = str_to_date + timedelta(days=1)
        end_date = real_end_date.strftime("%Y-%m-%d")

    result = None
    with HiddenPrints():
        lg = bs.login()
    if lg.error_code == '0':
        rs = bs.query_trade_dates(start_date=start_date, end_date=end_date)
        data_list = []
        while rs.error_code == '0' and rs.next():
            # 获取一条记录，将记录合并在一起
            data_list.append(rs.get_row_data())
        result = pd.DataFrame(data_list, columns=rs.fields)
        result = result.replace({'is_trading_day': {'1': True, '0': False}})
        # 结果集输出到csv文件
        result.to_csv("trade_datas.csv", encoding="gbk", index=False)
    else:
        msg = lg.error_msg
        logger.warning(f'logger in baostock with msg:{msg}')
    yield result
    # 登出系统
    with HiddenPrints():
        bs.logout()


if __name__ == '__main__':
    with trade_days_gen('2020-01-01', '2020-01-01') as days:
        ret = days.to_dict(orient='records')
        print(ret)
        for item in ret:
            print(f"date:{item['calendar_date']},    {item['is_trading_day']}")

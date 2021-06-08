#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/6/7 17:47
import baostock as bs
import pandas as pd
from contextlib import contextmanager
from datetime import timedelta
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.libs import convert


@contextmanager
def trade_days(start_date: str, end_date: str):
    str_to_date = convert.try_parse_date(end_date)
    delta = timedelta(days=1)
    real_end_date = str_to_date+delta
    real_end_date_str = real_end_date.strftime("%Y-%m-%d")

    result = None
    lg = bs.login()
    if lg.error_code == '0':
        rs = bs.query_trade_dates(start_date=start_date, end_date=real_end_date_str)
        data_list = []
        while rs.error_code == '0' and rs.next():
            # 获取一条记录，将记录合并在一起
            print(rs.get_row_data())
            data_list.append(rs.get_row_data())
        result = pd.DataFrame(data_list, columns=rs.fields)
        result = result.replace({'is_trading_day': {'1': True,
                                                    '0': False}})
        # 结果集输出到csv文件
        result.to_csv("trade_datas.csv", encoding="gbk", index=False)
    else:

        msg = lg.error_msg
        logger.warning(f'logger in baostock with msg:{msg}')
    yield result
    # 登出系统
    bs.logout()


if __name__ == '__main__':
    with trade_days('2017-01-01', '2017-06-30') as days:
        ret = days.to_dict(orient='records')
        print(ret)

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/15 11:04
"""see also:
1. [做时间的朋友，必须知道收益咋算 | Python技术](http://www.justdopython.com/2021/01/04/python-rate-of-return/)
2. [Python数据分析_Numpy中的金融函数 - 简书](https://www.jianshu.com/p/9ad131856078)
终值                  fv
现值                  pv
净现值                npv
每期支付金额          pmt
内部收益率            irr
修正内部收益率        mirr
定期付款期数          nper
利率                  rate
"""
from typing import Union
import datetime

import numpy_financial as npf

from fundmate.libs import convert


def compound_interest(principal: Union[int, float], percent_rate_in_year: Union[int, float, str],
                      year: Union[int, float]):
    """
    复利计算
    :return:
    """
    if isinstance(percent_rate_in_year, str):
        if percent_rate_in_year.endswith('%'):
            float_rate_in_year = convert.percent2float(percent_rate_in_year)
        else:
            float_rate_in_year = float(percent_rate_in_year) / 100
    else:
        float_rate_in_year = percent_rate_in_year / 100

    return principal * (1 + float_rate_in_year) ** year


def aip(rate_in_month, nper, pmt, pv, when):
    """

    定投收益
    按月定投，每月定投 1000，月收益率为 10%，定投 12 个月，即一年的最终金额是:
    npf.fv(0.1, 12, -1000, 0)


    :param rate_in_month:月收益率
    :param nper:投资期数
    :param pmt:每期定投金额,负数表示投入，正数表示赎回
    :param pv:期初已有金额，即现值
    :param when:表示各期计算收益的时间点，期初为 0，期末为 1，默认为期末
    :return:
    """
    pass


def goal_to_money():
    """
    比如一年后要得到 5万元，计算每月的投入:
    npf.pmt(0.1, 12, 0, 50000)
    pmt 与 fv 的区别只是后面的两个参数含义不同

分别是，期初金额和终值金额
    :return:
    """
    pass


def know_date_but_no_amount(pmt_lists):
    """
    http://www.justdopython.com/2021/01/04/python-rate-of-return/#%E5%AE%9A%E6%9C%9F%E4%B8%8D%E5%AE%9A%E9%A2%9D%E7%9A%84%E6%94%B6%E7%9B%8A%E7%8E%87
    定期不定额:
    import numpy_financial as npf
pmts = [-1000, 100, -1300, -2000, 5200]
npf.irr(pmts)
# 0.10969579295711918
    :return:
    """
    # invest_seq = [-1000, 100, -1300, -2000, 5200]
    return npf.irr(pmt_lists)


def no_date_no_amount(datetime_seq, invest_seq):
    """
    dates = [datetime.date(2019, 2, 4),
             datetime.date(2019, 6, 17),
             datetime.date(2019, 11, 18),
             datetime.date(2020, 4, 27),
             datetime.date(2020, 10, 19)]

    values = [-300.3, -500.5, 741.153, -600.6, 1420.328547]

    xirr(values, dates)
    # 输出为: 0.779790640991537
    :param datetime_seq:
    :param invest_seq:
    :return:
    """
    assert len(datatime_seq) == len(invest_seq)
    pass

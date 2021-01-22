#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/15 11:34

# Copyright (c) 2012 Sutoiku, Inc. (MIT License)

# Some algorithms have been ported from Apache OpenOffice:

# /**************************************************************
#  *
#  * Licensed to the Apache Software Foundation (ASF) under one
#  * or more contributor license agreements.  See the NOTICE file
#  * distributed with this work for additional information
#  * regarding copyright ownership.  The ASF licenses this file
#  * to you under the Apache License, Version 2.0 (the
#  * "License"); you may not use this file except in compliance
#  * with the License.  You may obtain a copy of the License at
#  *
#  *   http://www.apache.org/licenses/LICENSE-2.0
#  *
#  * Unless required by applicable law or agreed to in writing,
#  * software distributed under the License is distributed on an
#  * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#  * KIND, either express or implied.  See the License for the
#  * specific language governing permissions and limitations
#  * under the License.
#  *
#  *************************************************************/
"""
see also:
- [Tacombel/XIRR.py: XIRR function for PYTHON](https://github.com/Tacombel/XIRR.py)
- [tarioch/xirr](https://github.com/tarioch/xirr/)
- [peliot/XIRR-and-XNPV: python implementation of Microsoft Excel's XNPV and XIRR](https://github.com/peliot/XIRR-and-XNPV)
- [XIRR: How to calculate your returns](https://www.indiainfoline.com/article/research-articles/xirr-how-to-calculate-your-returns-38115077_1.html)
- [financial python library that has xirr and xnpv function? - Stack Overflow](https://stackoverflow.com/questions/8919718/financial-python-library-that-has-xirr-and-xnpv-function)
- [计算XIRR_喜东东的博客-CSDN博客_xirr计算原理](https://blog.csdn.net/qq_34105362/article/details/89146711)
- [pandas - Calculating XIRR in Python - Stack Overflow](https://stackoverflow.com/questions/46668172/calculating-xirr-in-python)
test:
- [RayDeCampo/nodejs-xirr: Compute the internal rate of return of a sequences of transactions made at irregular periods.](https://github.com/RayDeCampo/nodejs-xirr)
- 1. [做时间的朋友，必须知道收益咋算 | Python技术](http://www.justdopython.com/2021/01/04/python-rate-of-return/)
- 2. [Python数据分析_Numpy中的金融函数 - 简书](https://www.jianshu.com/p/9ad131856078)

终值                  fv
现值                  pv
净现值                npv
每期支付金额          pmt
内部收益率            irr
修正内部收益率        mirr
定期付款期数          nper
利率                  rate
"""
import datetime
from typing import Union

import numpy_financial as npf

from backend.fundmate.libs import convert


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


class IRR:
    """
    修正内部收益率
    know_date_but_no_amount
    """

    def __init__(self):
        pass

    def __call__(self,pmt_lists):
        return npf.irr(pmt_lists)


class XIRR:
    """
    Credits: algorithm inspired by Apache OpenOffice
    """

    @staticmethod
    def years_between_dates(date1, date2) -> float:
        delta = date2 - date1
        return delta.days / 365

    def irr_result(self, values, dates, rate) -> float:
        """
        # Calculates the resulting amount
        :param values:
        :param dates:
        :param rate:
        :return:
        """
        r = rate + 1
        result = values[0]
        for i in range(1, len(values)):
            result = result + values[i] / pow(
                r, self.years_between_dates(dates[0], dates[i]))
            i += 1
        return result

    def first_derivation(self, values, dates, rate):
        """
        Calculates the first derivation
        :param values:
        :param dates:
        :param rate:
        :return:
        """
        r = rate + 1
        result = 0
        for i in range(1, len(values)):
            frac = self.years_between_dates(dates[0], dates[i])
            result = result - frac * values[i] / pow(r, frac + 1)
            i += 1
        return result

    def xirr(self, values, dates):
        """
        Check that values contains at least one positive value and one negative value
        [pandas - Python IRR Function giving different result than Excel XIRR - Stack Overflow](https://stackoverflow.com/questions/63797804/python-irr-function-giving-different-result-than-excel-xirr)
        :param values:
        :param dates:
        :return:
        """
        positive = False
        negative = False
        for v in values:
            if v > 0:
                positive = True
            if v < 0:
                negative = True

        # Return error if values does not contain at least one positive value and one negative value
        if not (positive and negative):
            return 'Error'
        # Initialize guess and resultRate
        guess = 0.1
        resultRate = guess

        # Set maximum epsilon for end of iteration
        epsMax = 1e-10

        # Set maximum number of iterations
        iterMax = 20

        # Implement Newton's method
        iteration = 0
        contLoop = True
        while contLoop and (iteration < iterMax):
            resultValue = self.irr_result(values, dates, resultRate)
            newRate = resultRate - (
                    resultValue / self.first_derivation(values, dates, resultRate))
            epsRate = abs(newRate - resultRate)
            resultRate = newRate
            if resultRate < -1:
                resultRate = -0.999999999
            contLoop = (epsRate > epsMax) and (abs(resultValue) > epsMax)
            iteration += 1
        if contLoop:
            return epsRate > epsMax, epsRate, 'iterMax'
        return resultRate


if __name__ == '__main__':
    values = [-18990, -23320, 49490]
    dates = [
        datetime.date(2016, 2, 5),
        datetime.date(2018, 1, 26),
        datetime.date(2018, 6, 5)
    ]
    x = XIRR()
    print(x.xirr(values, dates))

    pmts = [-1000, 100, -1300, -2000, 5200]
    irr = IRR()
    ret = irr(pmts)
    print(ret)

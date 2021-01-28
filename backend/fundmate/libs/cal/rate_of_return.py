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
- [peliot/XIRR-and-XNPV: python implementation of Microsoft Excel's XNPV and XIRR](https://github.com/peliot/XIRR-and-XNPV/)
- [tarioch/xirr](https://github.com/tarioch/xirr/)
- [Tacombel/XIRR.py: XIRR function for PYTHON](https://github.com/Tacombel/XIRR.py)

终值                 fv
现值                 pv
净现值               npv
每期支付金额          pmt
内部收益率            irr
内部收益率            xirr
修正内部收益率        mirr
定期付款期数          nper
利率                 rate
"""
import datetime
import locale
from functools import partial
from typing import Iterable, List, Union

import dateparser
import scipy.optimize
from deprecated import deprecated
import numpy_financial as npf

from backend.fundmate.libs import convert
from . import cal_except as calex

DAYS_PER_YEAR = 365.0
MONTH_PER_YEAR = 12


def try_parse_date(text: str):
    """
    try and parse date
    :param text: string
    :return: date part of datetime object
    """
    parse_ret = dateparser.parse(text)
    if parse_ret:
        return parse_ret.date()
    else:
        raise calex.ParseError(
            f'Can not parse {text},please check whether is a date like str?')


def try_parse_number(text: str) -> Union[int, float]:
    """
    parse string to int/float
    >>> try_parse_number('2000.12')
    >>> 2000.12

    >>> try_parse_number('200,012')
    >>> 200012

    >>> try_parse_number('200,012.12')
    >>> 200012.12

    >>> try_parse_number('20,012.12')
    >>> 20012.12
    :param text:
    :return:
    """
    if ',' in text:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        if '.' in text:
            val = locale.atof(text)
        else:
            val = locale.atoi(text)
    else:
        if '.' in text:
            val = float(text)
        else:
            val = int(text)
    return val


def merge_date_amount_map(date_seq, amount_seq):
    """
    如果用户给的是的两个列表，则先合并然后组装成以date为key的字典
    >>> dates = [
        '2008/1/1',
        '2008/3/1',
        '2008/10/30',
        '2009/2/15',
        '2009/4/1',
    ]
    >>> vals = [
        '-10,000',
        '2,750',
        '4,250',
        '3,250',
        '2,750',
    ]
    >>> merge_date_amount_map(dates,vals)

    {datetime.date(2008, 1, 1): -10000,
        datetime.date(2008, 3, 1): 2750,
        datetime.date(2008, 10, 30): 4250,
        datetime.date(2009, 2, 15): 3250,
        datetime.date(2009, 4, 1): 2750
        }
    :param date_seq:
    :param amount_seq:
    :return:
    """
    if isinstance(date_seq[0], str):
        _dates_parsed = list(map(try_parse_date, date_seq))
    else:
        _dates_parsed = date_seq
    if isinstance(amount_seq[0], str):
        _values_parsed = list(map(try_parse_number, amount_seq))
    else:
        _values_parsed = amount_seq
    return dict(zip(_dates_parsed, _values_parsed))


class ComputeConvert:
    """
    计算并转换
    """
    @staticmethod
    def convert_is_end_pay(
            when: Union[str, bool, int]) -> Union[str, bool, int]:
        """
        when con be bool
        'end': 0, 'begin': 1
        :param when:
        :return:
        """
        return int(not when) if isinstance(when, bool) else when

    @staticmethod
    def convert_year_rate_to_month(rate_in_year):
        return rate_in_year / MONTH_PER_YEAR

    @staticmethod
    def number_of_periods(year: Union[int, float]):
        """
        将年份转换为月份
        :param year:
        :return:
        """
        return year * MONTH_PER_YEAR


def compound_interest(principal: Union[int, float],
                      percent_rate_in_year: Union[int, float, str],
                      year: Union[int, float]):
    """
    复利计算
    :param principal: 本金
    :param percent_rate_in_year: 年化
    :param year: 时间年
    :return:
    """
    if isinstance(percent_rate_in_year, str):
        if percent_rate_in_year.endswith('%'):
            float_rate_in_year = convert.percent2float(percent_rate_in_year)
        else:
            float_rate_in_year = float(percent_rate_in_year) / 100
    else:
        float_rate_in_year = percent_rate_in_year / 100

    return principal * (1 + float_rate_in_year)**year


class EAR:
    """
    Effective Annual Percentage Rate
    有效年利率：指在按照给定的计息期利率和每年复利次数计算利息时，能够产生相同结果的每年复利一次的年利率。
    [有效年利率 - MBA智库百科](https://wiki.mbalib.com/wiki/%E6%9C%89%E6%95%88%E5%B9%B4%E5%88%A9%E7%8E%87)
    """
    def __call__(self, rate_in_month: Union[int, float]) -> Union[int, float]:
        return (1 + rate_in_month)**MONTH_PER_YEAR - 1


class RATE(ComputeConvert):
    """
    计算年金每期利率，算出来的结果为月收益，如果要算年收益需要导入EAR
    Compute the rate of interest per period.
    """
    def __call__(self,
                 year: int,
                 pmt: Union[int, float],
                 pv: Union[int, float],
                 fv: Union[int, float] = 0,
                 is_end_pay: Union[str, bool, int] = True,
                 guess: Union[int, float, None] = None,
                 tol: Union[int, float, None] = None,
                 maxiter: int = 100):
        """
        >>> rate = RATE()
        >>> rate(3,-1000,10000,0)
        0.09635443543378829

        :param year:
        :param pmt:
        :param pv:
        :param fv:
        :param is_end_pay:
        :param guess:
        :param tol:
        :param maxiter:
        :return:
        """
        nper = self.number_of_periods(year)
        when = self.convert_is_end_pay(is_end_pay)
        return npf.rate(nper,
                        pmt,
                        pv,
                        fv,
                        when=when,
                        guess=guess,
                        tol=tol,
                        maxiter=maxiter)


class FV(ComputeConvert):
    """
    年金终值：用于根据固定利率计算投资的未来值。可以将 FV 与定期付款、固定付款或一次付清总额付款结合使用
    Compute the future value.
    """
    def __call__(self,
                 rate_in_year: Union[int, float],
                 year: int,
                 pmt: Union[int, float],
                 pv: Union[int, float] = 0,
                 is_end_pay: Union[str, bool, int] = True):
        """
        用于计算理想状态下（即：只存不取）的定投收益
        以年化10%的收益率投资30年，每个月投入3000元，计算收益：
        >>> fv = FV()
        # 月末投资
        >>> fv(0.1, 30, -3000, 0)
        6781463.774388182
        ## 初始投资3000元
        >>> fv(0.1, 30, -3000, -3000)
        6840975.972508083
        # 月初投资
        >>> fv(0.1, 30, -3000, -3000, False)
        6897488.170627985
        ## 初始无投资
        >>> fv(0.1, 30, -3000, 0, False)
        6837975.972508084

        :param rate_in_year:年化收益率
        :param year:投资期数
        :param pmt:每期定投金额,负数表示投入，正数表示赎回
        :param pv:期初已有金额，即现值
        :param is_end_pay:bool,如果每月在月末投资，则is_end_pay为True,注意相应的pv值，第一个月开始时投入100元则为-100
        :return:
        """
        rate = self.convert_year_rate_to_month(rate_in_year)
        nper = self.number_of_periods(year)
        when = self.convert_is_end_pay(is_end_pay)

        return npf.fv(rate, nper, pmt, pv, when=when)


class PMT(ComputeConvert):
    """
    根据固定付款额和固定利率计算贷款的付款额。
    如：解决按揭买房房贷计算问题、3年后的一次旅行
    """
    def __call__(self,
                 rate_in_year: Union[int, float],
                 year: Union[int, float],
                 pv: Union[int, float],
                 fv: Union[int, float] = 0,
                 is_end_pay: Union[str, bool, int] = True):
        """
        M同学以年化4.9%的贷款利率(rate_in_year)以首付3成的方式购买一套面积100平，单价150000的房子，贷款周期30年（year）:
        则pv = 100*150000*(1-0.3)        # 1050000
        其中需要贷款金额（pv）1050000，
        到还完贷款（fv=0），他需要每个月还贷款多少钱？

        >>> pmt = PMT()
        >>> pmt(0.049,30,1050000)
        -5572.630566539454

        :param rate_in_year:
        :param year:
        :param pv:
        :param fv:
        :param is_end_pay:
        :return:
        """
        rate = self.convert_year_rate_to_month(rate_in_year)
        nper = self.number_of_periods(year)
        when = self.convert_is_end_pay(is_end_pay)
        return npf.pmt(rate, nper, pv, fv, when=when)


class PerConvert:
    @staticmethod
    def per_convert(year, per=None):
        if isinstance(per, (int, list)):
            return per
        elif per is None:
            return list(range(1, year + 1))


class PPMT(ComputeConvert, PerConvert):
    """
    根据贷款额计算还款额中的本金
    """
    def __call__(self,
                 rate_in_year: Union[int, float],
                 per: Union[int, float, None, List[Union[int, float]]],
                 year: Union[int, float],
                 pv: Union[int, float],
                 fv: Union[int, float] = 0,
                 is_end_pay: Union[str, bool, int] = True):
        """
        # 计算某一特定期（第一期为1，依次累加）月供中的本金：
        >>> ppmt = PPMT()
        >>> ppmt(0.049,3,30,1050000)
        -1295.6472272668188
        # 计算前三期
        >>> ppmt(0.049,[1,2,3],30,1050000)
        >>> array([-1285.13056654, -1290.37818302, -1295.64722727])

        # 计算每一期月供中的本金
        >>> ppmt(0.049,None,30,1050000)

        array([-1285.13056654, -1290.37818302, -1295.64722727, -1300.93778678,
               -1306.24994941, -1311.58380337, -1316.93943723, -1322.31693993,
               -1327.71640077, -1333.13790941, -1338.58155587, -1344.04743056,
               -1349.53562423, -1355.04622803, -1360.57933346, -1366.13503241,
               -1371.71341712, -1377.31458024, -1382.93861478, -1388.58561412,
               -1394.25567205, -1399.94888271, -1405.66534065, -1411.40514079,
               -1417.16837844, -1422.95514932, -1428.76554952, -1434.59967551,
               -1440.45762419, -1446.33949282])

        :param rate_in_year:
        :param per:允许空值
        :param year:
        :param pv:
        :param fv:
        :param is_end_pay:
        :return:
        """
        rate = self.convert_year_rate_to_month(rate_in_year)
        per = self.per_convert(year, per=per)
        nper = self.number_of_periods(year)
        when = self.convert_is_end_pay(is_end_pay)
        return npf.ppmt(rate, per, nper, pv, fv, when=when)


class IPMT(ComputeConvert, PerConvert):
    """
    根据贷款额计算还款额中的利息
    Compute the interest portion of a payment
    与 PPMT 接收值相同，不再赘述
    """
    def __call__(self,
                 rate_in_year: Union[int, float],
                 per: Union[int, List[int], None],
                 year: Union[int, float],
                 pv: Union[int, float],
                 fv: Union[int, float] = 0,
                 is_end_pay: Union[str, bool, int] = True):
        """
        >>> ipmt = IPMT()
        >>> ipmt(0.049,None,30,1050000)

        array([-4287.5       , -4282.25238352, -4276.98333927, -4271.69277976,
               -4266.38061713, -4261.04676317, -4255.69112931, -4250.31362661,
               -4244.91416577, -4239.49265713, -4234.04901067, -4228.58313598,
               -4223.09494231, -4217.58433851, -4212.05123308, -4206.49553413,
               -4200.91714942, -4195.3159863 , -4189.69195176, -4184.04495242,
               -4178.37489449, -4172.68168383, -4166.96522589, -4161.22542575,
               -4155.46218809, -4149.67541722, -4143.86501702, -4138.03089103,
               -4132.17294235, -4126.29107372])

        :param rate_in_year:
        :param per:
        :param year:
        :param pv:
        :param fv:
        :param is_end_pay:
        :return:
        """
        rate = self.convert_year_rate_to_month(rate_in_year)
        per = self.per_convert(year, per=per)
        nper = self.number_of_periods(year)
        when = self.convert_is_end_pay(is_end_pay)
        return npf.ipmt(rate, per, nper, pv, fv, when=when)


class PV(ComputeConvert):
    """
    计算现值
    要为未来确定时长的某项活动存够一定的目标值金额，已知年化，求开户存入金额
    >>> pv = PV()
    >>> pv(0.04,3,-800,30000)
    >>> 483.6897793911912

    """
    def __call__(self,
                 rate_in_year: Union[int, float],
                 year: Union[int, float],
                 pmt,
                 fv: Union[int, float] = 0,
                 is_end_pay: Union[str, bool, int] = True):
        """
        :param rate_in_year:
        :param year:
        :param pmt:
        :param fv:
        :param is_end_pay:
        :return:
        """
        rate = self.convert_year_rate_to_month(rate_in_year)
        nper = self.number_of_periods(year)
        when = self.convert_is_end_pay(is_end_pay)
        return npf.pv(rate, nper, pmt, fv=fv, when=when)


class NPER(ComputeConvert):
    """
    计算还款
    假设“卜利索”有有一笔 2,500 美元的个人贷款，约定为每月付款 150 美元，年利率为 3%。
    >>> nper = NPER()
    >>> nper(0.03,-150,2500)
    array(17.04511672)
    """
    def __call__(self,
                 rate_in_year: Union[int, float],
                 pmt: Union[int, float],
                 pv: Union[int, float],
                 fv: Union[int, float] = 0,
                 is_end_pay: Union[str, bool, int] = True):
        """
        :param rate_in_year:
        :param pmt:
        :param fv:
        :param is_end_pay:
        :return:
        """
        rate = self.convert_year_rate_to_month(rate_in_year)
        when = self.convert_is_end_pay(is_end_pay)
        return npf.nper(rate, pmt, pv, fv=fv, when=when)


class NPV:
    """
    npv = NPV()
    ret = npv(0.281,[-100, 39, 59, 55, 20])
    -0.00847859163845488
    """
    def __call__(self, rate: Union[int, float], values: Iterable):
        """
        :param rate:scalar数值，折现率。
        :param values:现金流。正数代表`收入`，负数代表 `投资`
        第一个值必须是初始的投资，也就是必须是负数
        :return:
        """
        return npf.npv(rate, values)


class IRR:
    """
    内部收益率，适用于定期不定额
    know_date_but_no_amount
    >>> pmts = [-1000, 100, -1300, -2000, 5200]
    >>> irr = IRR()
    >>> irr(pmts)
    0.10969579295711918
    """
    def __init__(self):
        pass

    def __call__(self, pmt_lists):
        return npf.irr(pmt_lists)


class XIRRDeprecated:
    """
    不一定定期发生的现金流的内部收益率
    no date no amount
    Credits: algorithm inspired by Apache OpenOffice
    """
    @staticmethod
    def years_between_dates(date1, date2) -> float:
        delta = date2 - date1
        return delta.days / 365

    def irr_result(self, values, dates, rate: Union[int, float]) -> float:
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

    def first_derivation(self, values, dates, rate: Union[int, float]):
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

    @deprecated(
        version='1.0.0',
        reason=
        "This implementation is simple and does not handle cases where there is no solution."
        "\nUsers requiring a more robust version should use scipy package "
        "optimize.newton.just use xirr.")
    def xirr(self, values, dates):
        """
        如果没有安装scipy可以使用分割法去获取一个有答案的值，
        this is a quick and dirty implementation of the secant method that works the same as the scipy function when
        there is an answer but does not fail gracefully when no answer is found. The version of XIRR using the
        locally defined secant_xirr is commented out, uncomment to use it.

        Check that values contains at least one positive value and one negative value

        dates = [datetime.date(2019, 2, 4),
                 datetime.date(2019, 6, 17),
                 datetime.date(2019, 11, 18),
                 datetime.date(2020, 4, 27),
                 datetime.date(2020, 10, 19)]

        values = [-300.3, -500.5, 741.153, -600.6, 1420.328547]

        xirr(values, dates)
        # 输出为: 0.779790640991537
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
        # Initialize guess and result_rate
        guess = 0.1
        result_rate = guess

        # Set maximum epsilon for end of iteration
        eps_max = 1e-10

        # Set maximum number of iterations
        iter_max = 20
        esp_rate = None
        # Implement Newton's method
        iteration = 0
        cont_loop = True
        while cont_loop and (iteration < iter_max):
            result_value = self.irr_result(values, dates, result_rate)
            new_rate = result_rate - (result_value / self.first_derivation(
                values, dates, result_rate))
            esp_rate = abs(new_rate - result_rate)
            result_rate = new_rate
            if result_rate < -1:
                result_rate = -0.999999999
            cont_loop = (esp_rate > eps_max) and (abs(result_value) > eps_max)
            iteration += 1
        if cont_loop:
            return esp_rate > eps_max, esp_rate, 'iter_max'
        return result_rate


class MIRR:
    """
    修正内部收益率
    Modified internal rate of return
    """
    def __call__(self, values, finance_rate: Union[int, float],
                 reinvest_rate: Union[int, float]):
        """
        values : array_like,现金流（必须有一个正值和一个负值），第一个值可以看做是沉没成本。
        finance_rate : scalar,对现金流支付的利率
        reinvest_rate : scalar,再投资时收到的现金流量利率
        :return:float
        """
        return npf.mirr(values, finance_rate, reinvest_rate)


'''
https://github.com/tarioch/xirr
based on https://stackoverflow.com/questions/8919718/financial-python-library-that-has-xirr-and-xnpv-function
with some handling for special cases from
https://github.com/RayDeCampo/java-xirr/blob/master/src/main/java/org/decampo/xirr/Xirr.java
'''


class XNPV:
    def __call__(self, values_per_date, rate: Union[int, float]):
        return self.xnpv(values_per_date, rate)

    @staticmethod
    def xnpv(values_per_date, rate: Union[int, float]):
        """
        Calculate the net present value of a series of cashflows at irregular intervals.
        Notes ---------------
        * The Net Present Value is the sum of each of cash flows discounted back to the date of the first cash flow. The
        discounted value of a given cash flow is A/(1+r)**(t-t0), where A is the amount, r is the discout rate,
        and (t-t0) is the time in years from the date of the first cash flow in the series (t0) to the date of the
        cash flow being added to the sum (t).
        * This function is equivalent to the Microsoft Excel function of the same name.
        >>> from datetime import date
        >>> date_amounts = {date(2019, 12, 31): -100, date(2020, 12, 31): 110}
        >>> xnpv = XNPV()
        >>> xnpv(date_amounts, -0.10)
        # 22.257507852701295

        :param values_per_date:a dict object in which each element is a tuple of the form (date, amount), where date
        is a python datetime.date object and amount is an integer or floating point number. Cash outflows (
        investments) are represented with negative amounts, and cash inflows (returns) are positive amounts.
        :param rate:the discount rate to be applied to the cash flows
        :return: a single value which is the NPV of the given cash flows.
        """
        if rate == -1.0:
            return float('inf')

        t0 = min(values_per_date.keys())

        if rate <= -1.0:
            return sum([
                -abs(vi) / (-1.0 - rate)**((ti - t0).days / DAYS_PER_YEAR)
                for ti, vi in values_per_date.items()
            ])

        return sum([
            vi / (1.0 + rate)**((ti - t0).days / DAYS_PER_YEAR)
            for ti, vi in values_per_date.items()
        ])


class XIRR:
    """
    注意：date应该升序排列
    """
    def __call__(self, values_per_date):
        return self.xirr(values_per_date)

    def secant_xirr(self, values, dates):
        """
        """
        xirr_deprecated = XIRRDeprecated()
        return xirr_deprecated.xirr(values, dates)

    @staticmethod
    def xirr(values, dates):
        """Calculate the irregular internal rate of return.

        >>> from datetime import date
        >>> dam = {date(2019, 12, 31): -80005.8, date(2020, 3, 12): 65209.6}
        >>> xirr(dam)
        -0.645363882724717
        """
        if len(values) != len(dates):
            raise calex.LenEqualError()
        values_per_date = merge_date_amount_map(dates, values)
        if not values_per_date:
            return None

        if all(v >= 0 for v in values_per_date.values()):
            return float("inf")
        if all(v <= 0 for v in values_per_date.values()):
            return -float("inf")

        x = XNPV()
        xnpv = x.xnpv
        xnpv_partial = partial(xnpv, values_per_date)
        '''
        def rate_func(r):
            """
            lambda r: xnpv(values_per_date, r)
            :param r:
            :return:
            """
            return xnpv(values_per_date, r)
        '''
        try:
            result = scipy.optimize.newton(xnpv_partial, 0)
        except (RuntimeError, OverflowError):  # Failed to converge try again
            result = scipy.optimize.brentq(xnpv_partial,
                                           -0.999999999999999,
                                           1e20,
                                           maxiter=10**6)

        if not isinstance(result, complex):
            return result
        else:
            return None

    def clean_xirr(self, values, dates):
        """A "cleaned" version of the xirr which avoids returning a xirr for some extreme cases and ignores amounts
        which are almost 0.
        """
        values_cleaned = [amount for amount in values if round(amount, 2) != 0]
        try:
            result = self.xirr(values_cleaned, dates)
        except ValueError:
            return None
        if result is not None and (abs(result) >= 100
                                   or round(result, 4) == 0):
            return None
        else:
            return result

    def df_xirr(self, df, date='date', amount='amount'):
        """
        see also: [Pass Pandas DataFrame as input · Issue #16 · tarioch/xirr](https://github.com/tarioch/xirr/issues/16)
        :param df: pandas df
        :param date: date column name
        :param amount: amount column name
        :return: xirr for given date and amount values
        """
        dates = df[date].tolist()
        amounts = df[amount].tolist()
        return self.xirr(amounts, dates)


if __name__ == '__main__':
    irr = IRR()
    pmts = [-100] * 12
    pmts.append(1440)
    ret = irr(pmts)
    print(f'irr:{ret}')  # 0.038655000965268194

    rate = RATE()
    rm = rate(1, -100, 0, 1440, is_end_pay=False)
    era = EAR()
    e = era(rm)
    print(f'rate:{rm},e:{e}')

    dates = []
    for i in range(1, 12 + 1):
        dates.append(datetime.date(2020, i, 1))
    dates.append(datetime.date(2021, 1, 1))
    xirr = XIRR()
    ret = xirr.xirr(pmts, dates)
    print(f'XIRR:{ret}')

    da = {
        datetime.date(2016, 1, 1): -50000,
        datetime.date(2016, 1, 10): 500,
        datetime.date(2016, 6, 1): 500,
        datetime.date(2016, 10, 25): 500,
        datetime.date(2016, 10, 27): 500,
        datetime.date(2017, 3, 1): 500,
        datetime.date(2017, 6, 15): 51000
    }
    dates = list(da.keys())
    pmts = list(da.values())
    ret = xirr.xirr(pmts, dates)
    print(f'XIRR:{ret}')

    xirrp = XIRRDeprecated()
    ret = xirrp.xirr(pmts, dates)
    print(f'XIRRDeprecated:{ret}')

    # fv = FV()
    # ret = fv(0.1, 30, -3000, 0)
    # print(ret)
    #
    da = {
        datetime.date(2016, 1, 1): -50000,
        datetime.date(2016, 1, 10): 500,
        datetime.date(2016, 6, 1): 500,
        datetime.date(2016, 10, 25): 500,
        datetime.date(2016, 10, 27): 500,
        datetime.date(2017, 3, 1): 500,
        datetime.date(2017, 6, 15): 51000
    }
    #
    # xirr = XIRR()
    # ret = xirr.xirr(da)
    # print(ret)

    # npv = NPV()
    # ret = npv(0.281,[-100, 39, 59, 55, 20])
    # ret = npv(0.0449, [-5000, 0, 0, 0, 0, 100, 100, 100, 100, 100, 6745]) #-284.1792672873844
    # ret = npv(0.0449, [-10000, 0, 0, 0, 0, 200, 200, 200, 200, 200, 13490])  # -568.3585345747688
    # print(ret)
    # -0.00847859163845488

    # print(ret)
    # values = [-18990, -23320, 49490]
    # dates = [
    #     datetime.date(2016, 2, 5),
    #     datetime.date(2018, 1, 26),
    #     datetime.date(2018, 6, 5)
    # ]
    # x = XIRR()
    # print(x.xirr(values, dates))
    # a = {
    #     datetime.date(2016, 1, 1): -50000,
    #     datetime.date(2016, 1, 10): 500,
    #     datetime.date(2016, 6, 1): 500,
    #     datetime.date(2016, 10, 25): 500,
    #     datetime.date(2016, 10, 27): 500,
    #     datetime.date(2017, 3, 1): 500,
    #     datetime.date(2017, 6, 15): 51000
    # }
    # dates = list(a.keys())
    # val = list(a.values())
    # print(dates, val)
    # x = XIRR()
    # print(x.xirr(val, dates))
    #
    dates = [
        datetime.date(2008, 1, 1),
        datetime.date(2008, 3, 1),
        datetime.date(2008, 10, 30),
        datetime.date(2009, 2, 15),
        datetime.date(2009, 4, 1),
    ]
    val = [
        -10000,
        2750,
        4250,
        3250,
        2750,
    ]
    x = XIRR()
    print(x.xirr(val, dates))

    # pmts = [-1000, 100, -1300, -2000, 5200]
    # irr = IRR()
    # ret = irr(pmts)
    # print(ret)

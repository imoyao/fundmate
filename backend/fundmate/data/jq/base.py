#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/6/23 16:55

# 克隆自聚宽文章：https://www.joinquant.com/post/14619
# 标题：有关获取交易日期（当前、前一天、前n天）及时间处理的Demo
# 作者：JoinQuant-Supercritical

import datetime

from jqdata import *
from jqlib.technical_analysis import *

""""
有关日期的问题：
（1）获取前n个交易日；
（2）有关日期的应用；
（3）datetime的常用方法；
（4）获取某日前或者后第几个交易日的方法
    目前可以获取2005-01-01~2018-12-31间的交易日，获取较多个交易日时请先估算下
    2018-11-20修改了未判断是否交易日的bug，感谢悠悠鱼同学
    2018-11-27修改了获取较多个交易日的问题，感谢哈咯同学
（5）获取去年的今天对应的日期
"""


def initialize(context):
    g.security = '000001.XSHE'
    g.n = 2

    # （3）测试datetime的常用方法
    print('=' * 50)
    print("测试datetime的常用方法:")
    simple_apply_datetime()

    # （4）测试下获取某日前或者后第几个交易日的方法
    print('=' * 50)
    print("测试下获取某日前或者后第几个交易日的方法:")
    print('-' * 50)
    # date = '2018-11-19'  # 交易日
    date = '2018-11-25'  # 非交易日
    count = 3

    is_before = True
    trade_day = get_before_after_trade_days(date, count, is_before)
    print("{0}前{1}个交易日为{2}".format(date, count, trade_day))
    print('-' * 50)

    is_before = False
    trade_day = get_before_after_trade_days(date, count, is_before)
    print("{0}后{1}个交易日为{2}".format(date, count, trade_day))

    # （5）获取去年的今天对应的日期
    print('=' * 50)
    get_last_year_date(context)


def handle_data(context, data):
    """（1）获取前n个交易日"""
    # 当前日期
    current_date = context.current_dt.date()
    print('当前日期为{0}'.format(current_date))
    # print(type(current_date))
    # 前一个交易日
    previous_date = context.previous_date
    print('前一个交易日为{0}'.format(previous_date))

    # print('-'*50)
    #
    # """（2）有关日期的应用"""
    # # 获取不同日期的KDJ(开盘时获取当天的技术指标会存在未来数据，应该获取前一天的)
    # K1,D1,J1 = KDJ(g.security, check_date=current_date, N =9, M1=3, M2=3)
    # K2,D2,J2 = KDJ(g.security, check_date=previous_date, N =9, M1=3, M2=3)
    # print(J1, J2)
    # print(J1[g.security])
    #
    # print('#'*50)


def simple_apply_datetime():
    """
    ## （3）datetime的常用方法
    :return:
    """
    # 打印现在的时间
    now = datetime.datetime.now()
    print("现在时间是:{0}".format(now))
    # 把datetime转成字符串
    print(now.strftime("%Y-%m-%d %H:%M:%S"))
    # 把字符串转成datetime
    str_time = '2018-08-08'
    print(datetime.datetime.strptime(str_time, "%Y-%m-%d"))
    # date转datetime
    date = datetime.date.today()
    print("今天的日期是：{0}".format(date))
    # datetime获取日期,前天日期
    yesterday = date + timedelta(days=-2)  # 减去两天
    print("前天的日期是：{0}".format(yesterday))
    # 获取今天是星期几
    week = date.isoweekday()
    print("今天是星期：{0}".format(week))


def get_before_after_trade_days(date, count, is_before):
    """
    获取某日前或者第几个交易日的方法
    目前只能获取2005-01-01到2019-12-31日的交易日，如果获取的日期较多时（例如一年252个），请先估算下是否超出这个范围
    todo:下次再修改超出这个日期范围的问题
    """
    # 得到该日期前n天的交易日
    _before_days = get_trade_days(end_date=date, count=count + 5)

    # 得到该日期后n天的交易日
    _end_date = datetime.datetime.strptime(str(date), '%Y-%m-%d')
    # 获取该天count*2天后日期作为end_date
    last_date = _end_date + datetime.timedelta(days=(count * 2 + 1))
    _after_days = get_trade_days(start_date=date, end_date=last_date)

    # 将date的格式转为datetime.date
    _date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    # 区分输入的日期是不是交易日
    if _date == _before_days[-1]:
        # print("输入的日期{0}为交易日...".format(date))
        before_days = _before_days[-1 - count]
        if count == 1:
            after_days = _after_days[1]
        else:
            after_days = _after_days[count]
    else:
        # print("输入的日期{0}不是交易日...".format(date))
        before_days = _before_days[-count]
        after_days = _after_days[count - 1]

    # 获取前还是后n个交易日
    if is_before:
        trade_day = before_days
    else:
        trade_day = after_days

    return trade_day


def get_last_year_date(context):
    """
    获取去年的今天对应的日期
        例如：现在是2018-08-15，则去年的今天是2017-08-15
    """
    now = context.current_dt
    last_one_year = int(now.year) - 1
    now_date = now.strftime("%Y-%m-%d")[-6:]
    last_year_date = str(last_one_year) + now_date
    print(last_year_date)
    return last_year_date

# -*- coding: utf-8 -*-
"""
Created on Thu Jul 12 09:52:52 2018

@author: 量小白
"""
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pyecharts.charts import Line
from scipy import interpolate

current_path = Path(__file__).parent.resolve()

shibor_rate = {}
options_data = {}
tradeday = {}
true_ivix = {}
try:
    with open(f'{str(current_path)}/shibor.csv', 'r', encoding='gbk') as f:
        shibor_rate = pd.read_csv(f, index_col=0, encoding='GBK')
except UnicodeDecodeError as e:
    print(e)

try:
    with open(f'{str(current_path)}/options.csv', 'r', encoding='gbk') as f:
        options_data = pd.read_csv(f, index_col=0, encoding='GBK')
except UnicodeDecodeError as e:
    print(e)

try:
    with open(f'{str(current_path)}/tradeday.csv', 'r', encoding='gbk') as f:
        tradeday = pd.read_csv(f, index_col=0, encoding='GBK')
except UnicodeDecodeError as e:
    print(e)

try:
    with open(f'{str(current_path)}/ivixx.csv', 'r', encoding='gbk') as f:
        true_ivix = pd.read_csv(f, index_col=0, encoding='GBK')
except UnicodeDecodeError as e:
    print(e)


# ==============================================================================
# 开始计算ivix部分
# ==============================================================================
def periods_spline_risk_free_interest_rate(options, date):
    """
    params: options: 计算VIX的当天的options数据用来获取expDate
            date: 计算哪天的VIX
    return：shibor：该date到每个到期日exoDate的risk free rate

    """
    date = datetime.strptime(date, '%Y/%m/%d')
    # date = datetime(date.year,date.month,date.day)
    exp_dates = np.sort(options.EXE_ENDDATE.unique())
    periods = {}
    for epd in exp_dates:
        epd = pd.to_datetime(epd)
        periods[epd] = (epd - date).days * 1.0 / 365.0
    shibor_date = datetime.strptime(shibor_rate.index[0], "%Y-%m-%d")
    if date >= shibor_date:
        date_str = shibor_rate.index[0]
        shibor_values = shibor_rate.ix[0].values
        # shibor_values = np.asarray(list(map(float,shibor_values)))
    else:
        date_str = date.strftime("%Y-%m-%d")
        shibor_values = shibor_rate.loc[date_str].values
        # shibor_values = np.asarray(list(map(float,shibor_values)))

    shibor = {}
    period = np.asarray([1.0, 7.0, 14.0, 30.0, 90.0, 180.0, 270.0, 360.0]) / 360.0
    min_period = min(period)
    max_period = max(period)
    for p in periods.keys():
        tmp = periods[p]
        if periods[p] > max_period:
            tmp = max_period * 0.99999
        elif periods[p] < min_period:
            tmp = min_period * 1.00001
        # 此处使用SHIBOR来插值

        # sh = interpolate.spline(period, shibor_values, tmp, order=3)
        sh = interpolate.interp1d(period, shibor_values)
        sh = sh(tmp)
        shibor[p] = sh / 100.0
    return shibor


def get_hist_day_options(vix_date, options_data):
    _options_data = options_data.loc[vix_date, :]
    return _options_data


def get_near_next_opt_exp_date(options, vix_date):
    """
    找到options中的当月和次月期权到期日；
    用这两个期权隐含的未来波动率来插值计算未来30隐含波动率，是为市场恐慌指数VIX；
    如果options中的最近到期期权离到期日仅剩1天以内，则抛弃这一期权，改
    选择次月期权和次月期权之后第一个到期的期权来计算。
    返回的near和next就是用来计算VIX的两个期权的到期日
    params: options: 该date为交易日的所有期权合约的基本信息和价格信息
            vix_date: VIX的计算日期
    return: near: 当月合约到期日（ps：大于1天到期）
            next：次月合约到期日
    """
    vix_date = datetime.strptime(vix_date, '%Y/%m/%d')
    options_exp_date = list(pd.Series(options.EXE_ENDDATE.values.ravel()).unique())
    options_exp_date = [datetime.strptime(i, '%Y/%m/%d %H:%M') for i in options_exp_date]
    near = min(options_exp_date)
    options_exp_date.remove(near)
    if near.day - vix_date.day < 1:
        near = min(options_exp_date)
        options_exp_date.remove(near)
    nt = min(options_exp_date)
    return near, nt


def get_strike_min_call_minus_put_close_price(options):
    """
    options 中包括计算某日VIX的call和put两种期权，
    对每个行权价，计算相应的call和put的价格差的绝对值，
    返回这一价格差的绝对值最小的那个行权价，
    并返回该行权价对应的call和put期权价格的差
    params:options: 该date为交易日的所有期权合约的基本信息和价格信息
    return: strike: 看涨合约价格-看跌合约价格 的差值的绝对值最小的行权价
            price_diff: 以及这个差值，这个是用来确定中间行权价的第一步
    """
    call = options[options.EXE_MODE == u"认购"].set_index(u"EXE_PRICE").sort_index()
    put = options[options.EXE_MODE == u"认沽"].set_index(u"EXE_PRICE").sort_index()
    call_minus_put = call.CLOSE - put.CLOSE
    strike = abs(call_minus_put).idxmin()
    price_diff = call_minus_put[strike].min()
    return strike, price_diff


def cal_sigma_square(options, FF, R, T):
    """
    计算某个到期日期权对于VIX的贡献sigma；
    输入为期权数据options，FF为forward index price，
    R为无风险利率， T为期权剩余到期时间
    params: options:该date为交易日的所有期权合约的基本信息和价格信息
            FF: 根据上一步计算得来的strike，然后再计算得到的forward index price， 根据它对所需要的看涨看跌合约进行划分。
                取小于FF的第一个行权价为中间行权价K0， 然后选取大于等于K0的所有看涨合约， 选取小于等于K0的所有看跌合约。
                对行权价为K0的看涨看跌合约，删除看涨合约，不过看跌合约的价格为两者的均值。
            R： 这部分期权合约到期日对应的无风险利率 shibor
            T： 还有多久到期（年化）
    return：Sigma：得到的结果是传入该到期日数据的Sigma
    """
    call_all = options[options.EXE_MODE == u"认购"].set_index(u"EXE_PRICE").sort_index()

    put_all = options[options.EXE_MODE == u"认沽"].set_index(u"EXE_PRICE").sort_index()
    call_all['deltaK'] = 0.05
    put_all['deltaK'] = 0.05
    # Interval between strike prices
    index = call_all.index
    if len(index) < 3:
        call_all['deltaK'] = index[-1] - index[0]
    else:
        for i in range(1, len(index) - 1):
            call_all['deltaK'].loc[index[i]] = (index[i + 1] - index[i - 1]) / 2.0
        call_all['deltaK'].loc[index[0]] = index[1] - index[0]
        call_all['deltaK'].loc[index[-1]] = index[-1] - index[-2]
    index = put_all.index
    if len(index) < 3:
        put_all['deltaK'] = index[-1] - index[0]
    else:
        for i in range(1, len(index) - 1):
            put_all['deltaK'].loc[index[i]] = (index[i + 1] - index[i - 1]) / 2.0
        put_all['deltaK'].loc[index[0]] = index[1] - index[0]
        put_all['deltaK'].loc[index[-1]] = index[-1] - index[-2]

    call = call_all[call_all.index > FF]
    put = put_all[put_all.index < FF]

    if put.empty:
        ff_idx = call.index[0]
        call_component = call.CLOSE * call.deltaK / call.index / call.index
        sigma = (sum(call_component)) * np.exp(T * R) * 2 / T
        sigma = sigma - (FF / ff_idx - 1)**2 / T
    elif call.empty:
        ff_idx = put.index[-1]
        put_component = put.CLOSE * put.deltaK / put.index / put.index
        sigma = (sum(put_component)) * np.exp(T * R) * 2 / T
        sigma = sigma - (FF / ff_idx - 1)**2 / T
    else:
        ff_idx = put.index[-1]

        try:
            if len(put_all.loc[ff_idx].CLOSE.values) > 1:
                put['CLOSE'].iloc[-1] = (put_all.loc[ff_idx].CLOSE.values[1] +
                                         call_all.loc[ff_idx].CLOSE.values[0]) / 2.0
        except:
            put['CLOSE'].iloc[-1] = (put_all.loc[ff_idx].CLOSE + call_all.loc[ff_idx].CLOSE) / 2.0

        call_component = call.CLOSE * call.deltaK / call.index / call.index
        put_component = put.CLOSE * put.deltaK / put.index / put.index
        sigma = (sum(call_component) + sum(put_component)) * np.exp(T * R) * 2 / T
        sigma = sigma - (FF / ff_idx - 1)**2 / T
    return sigma


def change_ste(t):
    if t.month >= 10:
        str_t = t.strftime('%Y/%m/%d ') + '0:00'
    else:
        str_t = t.strftime('%Y/%m/%d ')
        str_t = str_t[:5] + str_t[6:] + '0:00'
    return str_t


def cal_day_vix(vix_date):
    """
    利用CBOE的计算方法，计算历史某一日的未来30日期权波动率指数VIX
    params：vix_date：计算VIX的日期  '%Y/%m/%d' 字符串格式
    return：VIX结果
    """

    # 拿取所需期权信息
    options = get_hist_day_options(vix_date, options_data)
    near, nexts = get_near_next_opt_exp_date(options, vix_date)
    shibor = periods_spline_risk_free_interest_rate(options, vix_date)
    r_near = shibor[datetime(near.year, near.month, near.day)]
    r_next = shibor[datetime(nexts.year, nexts.month, nexts.day)]
    str_near = change_ste(near)
    str_nexts = change_ste(nexts)
    options_near_term = options[options.EXE_ENDDATE == str_near]
    options_next_term = options[options.EXE_ENDDATE == str_nexts]
    # time to expiration
    vix_date = datetime.strptime(vix_date, '%Y/%m/%d')
    t_near = (near - vix_date).days / 365.0
    t_next = (nexts - vix_date).days / 365.0
    # the forward index prices
    near_price_diff = get_strike_min_call_minus_put_close_price(options_near_term)
    next_price_diff = get_strike_min_call_minus_put_close_price(options_next_term)
    near_f = near_price_diff[0] + np.exp(t_near * r_near) * near_price_diff[1]
    next_f = next_price_diff[0] + np.exp(t_next * r_next) * next_price_diff[1]
    # 计算不同到期日期权对于VIX的贡献
    near_sigma = cal_sigma_square(options_near_term, near_f, r_near, t_near)
    next_sigma = cal_sigma_square(options_next_term, next_f, r_next, t_next)

    # 利用两个不同到期日的期权对VIX的贡献sig1和sig2，
    # 已经相应的期权剩余到期时间T1和T2；
    # 差值得到并返回VIX指数(%)
    w = (t_next - 30.0 / 365.0) / (t_next - t_near)
    vix = t_near * w * near_sigma + t_next * (1 - w) * next_sigma
    return 100 * np.sqrt(abs(vix) * 365.0 / 30.0)


if __name__ == '__main__':
    ivix = []
    for day in tradeday.index:
        ivix.append(cal_day_vix(day))
    attr = true_ivix[u'日期'].tolist()
    Line().add_xaxis(attr).add_yaxis("中证指数发布",
                                     true_ivix[u'收盘价(元)'].tolist(),
                                     is_smooth=True,
                                     markpoint_opts=['average', 'max'
                                                     ]).add_yaxis("公式计算数据", ivix, is_smooth=True,
                                                                  markline_opts=['max'
                                                                                 ]).render(f"{current_path}/vix.html")

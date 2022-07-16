#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/10 21:56
import ast
import datetime
from typing import Dict, List, Union

import dateparser
import pandas as pd
from deprecated import deprecated

from backend.fundmate import settings, utils
from backend.fundmate.data.baostock.base import trade_days_gen
from backend.fundmate.fund.models import DailyWorth, FeeRatio
from backend.fundmate.fund.schemas import PurchaseInfoSchema, RedeemInfoSchema


class FundMiddleWare:

    def __init__(self):
        pass

    def raw_purchase_info(self, fund_code: str) -> List:
        fee_ratio = FeeRatio.buy_info(fund_code=fund_code, op_type=settings.FeeTypeEnum.purchase)
        return fee_ratio

    def purchase_info(self, fund_code: str) -> Dict:
        """
        基金的申购费率信息
        :param fund_code:
        :return:
        """
        fee_ratio = self.raw_purchase_info(fund_code=fund_code)
        fr_out_schema = PurchaseInfoSchema(many=True)
        result = fr_out_schema.dump(fee_ratio)
        return result

    def match_purchase_rate(self, fund_code: str, amount: float):
        """
        根据购买的金额匹配到对应的购买费率/扣费金额（如果大于1）
        :param fund_code:
        :param amount:
        :return:
        """
        _purchase_info = self.purchase_info(fund_code)
        bins = [0]
        max_quota = float('inf')
        labels = []
        for item in _purchase_info:
            quota = item.get('end_quota')
            bins.append(quota)

            real_rate = item.get('real_rate')
            if quota == max_quota:
                real_rate = item.get('rule_fee_amount')
            labels.append(real_rate)

        if not bins[-1] == max_quota:
            bins.append(max_quota)
        data = [{'amount': amount}]
        df = pd.DataFrame(data)
        df['cal_rate'] = pd.cut(df['amount'], bins, right=False, labels=labels)
        ret = df.to_dict(orient='records')
        cal_rate = ret[0].get('cal_rate')
        return cal_rate

    def match_redeem_rate(self, fund_code: str, duration_day: float):
        """
        根据截止赎回确认日的天数匹配到对应的赎回费率
        :param fund_code:
        :param duration_day:
        :return:
        """
        _redeem_info = self.redeem_info(fund_code)
        bins = [0]
        max_quota = float('inf')
        labels = []
        for item in _redeem_info:
            day = item.get('end_day')
            # 如果不是最大值，则转为int
            if day != max_quota:
                day = int(day)
            bins.append(day)

            real_rate = item.get('real_rate')
            labels.append(real_rate)

        if not bins[-1] == max_quota:
            bins.append(max_quota)

        data = [{'day': duration_day}]
        df = pd.DataFrame(data)
        df['cal_rate'] = pd.cut(df['day'], bins, right=False, labels=labels)
        ret = df.to_dict(orient='records')
        cal_rate = ret[0].get('cal_rate')
        return cal_rate

    def raw_redeem_info(self, fund_code: str) -> List:
        fee_ratio = FeeRatio.redeem_info(fund_code=fund_code)
        return fee_ratio

    def redeem_info(self, fund_code: str) -> Dict:
        """
        基金的赎回费率信息
        :param fund_code:
        :return:
        """
        fee_ratio = self.raw_redeem_info(fund_code=fund_code)
        fr_redeem_schema = RedeemInfoSchema(many=True)
        result = fr_redeem_schema.dump(fee_ratio)
        return result

    def charge_amount(self, amount: Union[int, float] = 10000, charge_rate: float = 0.15):
        """
        申购费
        :return:
        """
        _real_amount = self.real_amount(amount, charge_rate)
        fee_value = amount - _real_amount
        return fee_value

    @staticmethod
    def real_amount(amount: Union[int, float] = 10000, charge_rate: float = 0.15):
        """
        净申购金额
        :return:
        """
        return amount / (1 + charge_rate / 100.0)

    def share_holders(self,
                      amount: Union[int, float] = 10000,
                      charge_rate: float = 0.15,
                      daily_value: Union[int, float] = 1):
        """
        申购份额
        :param daily_value:
        :param charge_rate:
        :param amount:
        :return:
        """
        # [python - Convert percent string to float in pandas read_csv - Stack Overflow](
        # https://stackoverflow.com/questions/25669588/convert-percent-string-to-float-in-pandas-read-csv)
        _real_amount = self.real_amount(amount, charge_rate)
        hold_value = _real_amount / daily_value
        return round(hold_value, 2)

    def cal_purchase_info(self,
                          amount: Union[int, float] = 10000,
                          charge_rate: float = 0.15,
                          daily_value: Union[int, float] = 1) -> dict:
        """
        基金申（认）购费用计算器：
        [基金申（认）购费用计算器 _  东方财富网](https://data.eastmoney.com/money/calc/CalcFundSGRG.html)
        >>> f =Fund()
        >>> f.cal_purchase_info(amount=3000, daily_value=5.5340)
        {'charge_amount': 4.49, 'real_amount': 2995.51, 'hold_value': 541.29}

        >>> f.cal_purchase_info(amount=3000, daily_value=5.2280)
        {'charge_amount': 4.49, 'real_amount': 2995.51, 'hold_value': 572.97}

        :param amount:
        :param charge_rate:
        :param daily_value:
        :return: charge_amount: 手续费     hold_value： 成交份额    real_amount：成交金额
        """
        _charge_amount = round(self.charge_amount(amount, charge_rate), 2)
        _real_amount = round(self.real_amount(amount, charge_rate), 2)
        _hold_value = self.share_holders(amount, charge_rate, daily_value)
        return {'charge_amount': _charge_amount, 'real_amount': _real_amount, 'hold_value': _hold_value}

    def cal_redeem_info(self,
                        portion: Union[int, float] = 10000,
                        charge_rate: float = 0.15,
                        daily_value: Union[int, float] = 1) -> dict:
        """
        正算：基金赎回费用计算器
        >>> f= FundMiddleWare()
        >>> f.cal_redeem_info(portion=3000, daily_value=5.2245)
        {'charge_amount': 23.51, 'real_amount': 15649.99}

        [基金赎回费用计算器 _ 理财计算器 _ 数据中心 _ 东方财富网](https://data.eastmoney.com/money/calc/CalcFundSH.html)
        :param portion: 赎回份额
        :param charge_rate:
        :param daily_value:
        :return: 手续费 + 赎回金额
        """
        _redeem_amount = portion * daily_value
        # 赎回手续费
        _charge_amount = _redeem_amount * charge_rate / 100.0
        rd_charge_amount = round(_charge_amount, 2)
        # 赎回金额
        _real_amount = round(_redeem_amount - _charge_amount, 2)
        return {'charge_amount': rd_charge_amount, 'real_amount': _real_amount}

    def check_is_redeem_able(self, hold_shares: float, redeem_shares: float):
        return hold_shares >= redeem_shares

    def get_share_distribution(self):
        """
        2019-02-28 in 1000		2020-03-05 out 1000
        2019-05-28 in 3000		2020-06-15 out 1000
        2019-12-28 in 5000		2020-07-15 out 1000
        2020-05-01 in 1000		2020-09-25 out 1000
        2021-05-30 in 1000		2021-03-05 out 1000

        :return:
        """
        pass

    def know_amount_cal_charge_fee(self, purchase_confirm_date: datetime, redeem_confirm_date: datetime,
                                   redeem_shares: float):
        """
        已知：赎回时的净值，赎回结算的金额
        需要进一步计算：赎回时的费率
        1. 持有天数
        2. 是否赎回大于现有份额？
        3. 判断赎回份额的费率分布 比如：赎回5000份，其中3000份持有3年+，1000份持有2年，500分持有1年内，1500分持有30天以内
        4. 每一部分分别计算，然后最后加起来
        see also:backend/fundmate/libs/redeem_fee
        返回：赎回的份额
        :return:
        """
        durations = utils.cal_durations(purchase_confirm_date, redeem_confirm_date)
        hold_shares = 1000  # TODO: 查询数据库获取持有的份额
        is_redeem_able = self.check_is_redeem_able(hold_shares, redeem_shares)
        return is_redeem_able, durations


@deprecated(version='1.0.0', reason='请使用天天基金接口：http://fund.eastmoney.com/tools/jiaoyiri.html')
class TradeDate:
    """
    与交易日相关的处理
    """

    def real_op_day(self, record_date: str) -> str:
        """
        获取有效操作日，如果是15点之后，则推到下一天，否则为当天
        ~~如果是从历史账单中导入，则记录时间为确认日，如果是用户手动填入，则不一定纪录日就是确认日~~
        :param record_date:记录单中的交易时间戳
        :return:
        """
        parse_ret = dateparser.parse(record_date)
        _date = parse_ret.date()
        # 15:00之后
        if parse_ret.hour >= 15:
            date = (_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            date = str(_date)
        return date

    @staticmethod
    def is_trade_day(date):
        """
        判断某一天是否为交易日
        :param date:
        :return:
        """
        if not isinstance(date, str):
            date = str(date)
        with trade_days_gen(date) as days:
            ret = days.to_dict(orient='records')
        return ret[0]['is_trading_day']

    def verify_date(self, t_date):
        """
        - T日
        T日指交易日，不包括周末和节假日，在T日基金销售公司会对投资者的申购、赎回、转换或者其他业务申请进行受理。
        T日是以股市收市时间为界限，比如周五15:00之后提交的交易视为下周一的交易，以下周一的净值成交，若在周五当天15:00之前提交的交易则按周五收市结束后当天的净值成交。

        - 基金持有时间
        基金份额持有时间自申购确认日开始计算。持有期为"赎回确认日期-申购确认日期"，即从申购
        确认日计算至赎回确认日的前一日。
        举个例子:
        小天周一15: 00前申购了A基金，基金公司在周二进行了确认，下周三15: 00前小天又进行了赎回操作，基金公司在周四进行了赎回确认，那么小天持有A基金的时间则为周二到下周三，一共9天，即赎回确认日不计入持有时间。
        基金持有期按照自然日计算

        - 自然日
        自然日是指正常的工作日和周末休息日，也包括所有假期。当然，基金持有时长(比如持有7天)便是按自然日来计算的。
        1. 判断输入日期（带时间）是否为T日，如果是，则判断下一天是否为t日，如果是，则确认日为下一天，如果不是，则继续往下找，直到找到交易日
        :return:
        """
        if self.is_trade_day(t_date):
            v_date = utils.tomorrow_date(t_date)
            # 如果当天是交易日，明天也是交易日，则为确认日
            if self.is_trade_day(v_date):
                return v_date
            else:
                # 明天不是交易日，则找到下一个交易日并返回
                return self.next_trade_day(v_date)
        else:
            # 当天不是交易日，则先找到交易日，然后再递归寻找确认日
            _date = self.next_trade_day(t_date)
            v_date = self.verify_date(_date)
            return v_date

    def next_trade_day(self, date: str) -> datetime.date:
        """
        寻找下一个交易日
        首先做tomorrow_date运算，如果明天是交易日，则返回，否则继续查找
        :param date: 日期
        :return:
        """
        tmr = utils.tomorrow_date(date)
        is_trade = self.is_trade_day(tmr)
        if is_trade:
            return tmr
        else:
            tmr = self.next_trade_day(tmr)
            return tmr


f = FundMiddleWare()
td = TradeDate()


class Booking:
    """
    记账功能涉及的操作，参考：
    1. “好买[基金账本 - 好买基金研究中心](https://www.howbuy.com/myfund/index.htm)”
    2. “同花顺投资账本”

    [记账功能设计与实现 | 基伴](https://fund.masantu.com/dev/bookkeeping.html#%E7%94%B3%E8%B4%AD)

    具体的操作类型定义参见：FUND_OP_TYPE
    """

    def hold_in(self,
                fund_code: str,
                d_time: str,
                is_prepay: bool = True,
                fee_rate: str = None,
                fee_amount: Union[int, float, str] = None,
                amount: Union[int, float, str] = None,
                count: Union[int, float, str] = None):
        """
        # FIXME: not finished
        申购/买入操作
        :param fund_code: 基金编码
        :param d_time: 带有时分秒的购买日期，注意：15:00之前还是之后非常重要，用户选择日期则默认12:00买入
        :param is_prepay: 收费方式，前端/后端收费
        :param fee_rate: 费率
        :param fee_amount: 收费数量
        :param amount:购买金额
        :param count:购买份额（一般根据数量和当日净值计算即可，允许用户修改，但是必须误差不太大）
        :return:
        """

        def str_to_float(convertable_var: Union[int, float, str]):
            if isinstance(convertable_var, str):
                return ast.literal_eval(convertable_var)
            return convertable_var

        fee_amount = str_to_float(fee_amount)  # noqa F811
        amount = str_to_float(amount)
        count = str_to_float(count)  # noqa F811
        d_val = DailyWorth.query(fund_id=fund_code, date=d_time).price  # noqa F811
        f.cal_purchase_info(amount)

    def redeem(
        self,
        fund_code: str,
    ):
        """
        赎回/卖出/支取
        """
        pass

    def transfer(self, from_fund: str, to_fund: str):
        """
        """
        pass

    def regular_invest(self):
        """
        """
        pass

    def bonus(self):
        """
        """
        pass

    def adjust(self):
        """
        TODO:
        这个是复制的支付宝的，对于用户应该是无感知的
        """
        pass

    def sale(self, fund_code: str):
        """赎回/卖出/支取"""
        pass


if __name__ == '__main__':
    print(f.cal_purchase_info(amount=3000, daily_value=5.5340))
    print(f.cal_purchase_info(amount=3000, daily_value=5.2280))
    print(f.cal_redeem_info(portion=3000, daily_value=5.2245, charge_rate=0))
    print(td.is_trade_day('2021-06-26'))
    print(td.verify_date('2020-06-24'))
    # =======================
    fund_code = '001718'
    p = f.purchase_info(fund_code)
    r = f.redeem_info(fund_code)
    print(p, r)

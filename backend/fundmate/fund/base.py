#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/10 21:56
import ast
from typing import Union

from .models import DailyWorth


class Fund:

    def __init__(self):
        pass

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

    def share_holders(self, amount: Union[int, float] = 10000,
                      charge_rate: float = 0.15, daily_value: Union[int, float] = 1):
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

    def purchase_info(self, amount: Union[int, float] = 10000,
                      charge_rate: float = 0.15, daily_value: Union[int, float] = 1
                      ):
        """
        购买信息
        :param amount:
        :param charge_rate:
        :param daily_value:
        :return:
        """
        _charge_amount = round(self.charge_amount(amount, charge_rate), 2)
        _real_amount = round(self.real_amount(amount, charge_rate), 2)
        _hold_value = self.share_holders(amount, charge_rate, daily_value)
        return {'charge_amount': _charge_amount, 'real_amount': _real_amount, 'hold_value': _hold_value}


f = Fund()


class Booking:
    """
    记账功能
    """
    pass

    def buy(self, fund_code: str, d_time: str, is_prepay: bool = True, fee_rate: str = None,
            fee_amount: Union[int, float, str] = None,
            amount: Union[int, float, str] = None,
            count: Union[int, float, str] = None):
        """
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

        fee_amount = str_to_float(fee_amount)
        amount = str_to_float(amount)
        count = str_to_float(count)
        d_val = DailyWorth.query(fund_id=fund_code, date=d_time).price
        f.purchase_info(amount)


if __name__ == '__main__':
    print(f.purchase_info(amount=3000, daily_value=5.5340))
    print(f.purchase_info(amount=3000, daily_value=5.2280))

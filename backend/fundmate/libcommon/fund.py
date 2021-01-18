#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/10 21:56
from typing import Union


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

    def real_amount(self, amount: Union[int, float] = 10000, charge_rate: float = 0.15):
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
        _charge_amount = round(self.charge_amount(amount, charge_rate), 2)
        _real_amount = round(self.real_amount(amount, charge_rate), 2)
        _hold_value = self.share_holders(amount, charge_rate, daily_value)
        return {'charge_amount': _charge_amount, 'real_amount': _real_amount, 'hold_value': _hold_value}


if __name__ == '__main__':
    f = Fund()
    print(f.purchase_info(amount=3000, daily_value=5.5340))
    print(f.purchase_info(amount=3000, daily_value=5.2280))

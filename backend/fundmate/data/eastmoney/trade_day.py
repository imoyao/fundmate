#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/30 11:03
@file: trade_day.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 交易日获取
"""
import re
from typing import Dict, Optional

import pyjson5
from xalpha.cons import rget

from backend.fundmate.data.eastmoney.base import BaseParse
from backend.fundmate.libs import convert


class TradeDay(BaseParse):
    """
    原始链接：http://fund.eastmoney.com/tools/jiaoyiri.html
    """
    url = 'http://fund.eastmoney.com/tools/DataHandler.aspx'

    def t_days(self, f_code: str, is_buy: bool = True) -> Optional[int]:
        """
        买卖基金时，获取t+n中的n是几，一般为1
        :param is_buy:
        :param f_code:
        :return:
        """
        ib = int(is_buy)
        params = {
            't': 't',
            'ib': ib,
            'fc': f_code,
        }
        resp = rget(self.url, params=params)
        regex = re.compile(r'.*={\s.*:"(\d)"};')
        reg_mat = self.match_resp(resp, regex)
        if reg_mat:
            t_day = int(reg_mat.groups()[0])
            return t_day

    def get_trade_info(self,
                       fund_code: str,
                       op_date: str,
                       is_buy: bool = True,
                       is_after_15o_clock=False) -> Optional[Dict]:
        """
        >>> td = TradeDay()
        >>> td.get_trade_info('163406', '2021-12-31')
         {'application_date': '2021-12-31', 'is_same_day': True, 'maturity': '2022-01-04', 'deadline': '2022-01-04'}

        ---
        申请日：2021-12-31

        申请所属交易日：2021-12-31（与申请日在同一交易日）

        确认日：2022-01-04

        >>> td.get_trade_info('163406', '2022-01-01')
        {'application_date': '2022-01-04', 'is_same_day': False, 'maturity': '2022-01-05', 'deadline': '2022-01-05'}

        ---
        申请日：2022-01-01

        申请所属交易日：2022-01-04（与申请日不在同一交易日）

        确认日：2022-01-05
        ---
        :param fund_code:
        :param op_date:
        :param is_buy:
        :param is_after_15o_clock:
        :return:
        """
        t_day = self.t_days(fund_code, is_buy=is_buy)
        is_after_deadline = int(is_after_15o_clock)

        params = {
            't': 'confirm',
            'date': op_date,
            'days': t_day,
            'after': is_after_deadline,
        }
        resp = rget(self.url, params=params)
        regex = re.compile(r'var\s*apidata\s*=\s*(.+);')
        reg_mat = self.match_resp(resp, regex)
        if reg_mat:
            _trade_info = reg_mat.groups()[0]
            trade_info = pyjson5.loads(_trade_info)
            raw_deadline = trade_info.get('deadline')
            raw_is_same = bool(int(trade_info.get('IsSame')))
            deadline = str(convert.try_parse_date(raw_deadline))
            trade_info['deadline'] = deadline
            trade_info['IsSame'] = raw_is_same
            new_keys = ['application_date', 'is_same_day', 'maturity', 'deadline']
            values = trade_info.values()
            result = dict(zip(new_keys, values))
            return result


if __name__ == '__main__':
    td = TradeDay()
    print(td.get_trade_info('163406', '2021-12-30'))

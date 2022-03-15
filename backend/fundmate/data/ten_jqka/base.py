#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/3/9 17:57
@file: base.py
@author: imoyao
@email: immoyao@gmail.com
@desc:
"""
from typing import Dict, List, Optional, Union

from xalpha.cons import rget_json


class FundInfo:

    def fund_name(self, fund_code: str) -> Optional[str]:
        """
        获取基金的全称：fd_full_name
        :param fund_code:
        :return:
        """
        url = f'http://fund.10jqka.com.cn/data/client/myfund/{fund_code}'
        resp = rget_json(url)
        if resp.get('error').get('id') == 0:
            base_info = resp.get('data')[0]
            fd_full_name = base_info.get('name')
            return fd_full_name


if __name__ == '__main__':
    ai_fund = FundInfo()
    assert ai_fund.fund_name('001718') == '工银物流产业股票A'

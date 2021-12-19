#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/16 11:09
@file: combination.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 爬取且慢基金的基金组合并保存到数据库，为后期跟踪策略提供数据
"""
from datetime import datetime
from typing import Dict, List, Optional

from xalpha.cons import rget_json

from backend.fundmate.data.qieman import utils


class Strategy:
    """
    以基金柠檬的远足为例：https://qieman.com/portfolios/ZH012926
    """

    def __init__(self):
        self.x_sign = utils.get_x_sign()
        self.headers = self.gen_headers()

    def get_latest_sign(self):
        """
        check by timestamp from sign, if expired update it.
        :return:
        """
        now = datetime.today()
        today = datetime(year=now.year, month=now.month, day=now.day)
        today_sign_ts = int(today.timestamp())
        _sign = self.x_sign
        origin_sign_ts = int(_sign[:10])
        if origin_sign_ts < today_sign_ts:
            _sign = utils.get_x_sign()
        return _sign

    def gen_headers(self):
        _headers = {
            'x-sign':
            self.get_latest_sign(),
            'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/98.0.4741.0 Safari/537.36',
        }
        return _headers

    def get(self):
        """获取所有组合"""
        pass

    def is_success(self, response: dict) -> bool:
        return response and response.get('result_code') == 0

    def detail(self, code: str = 'ZH000001') -> Optional[Dict]:
        """
        获取单个组合的信息
        :param code:
        :return:
        """
        url = f'https://qieman.com/pmdj/v1/pomodels/{code}'
        resp = rget_json(url, headers=self.headers)
        return resp

    def per_trading_remark(self, trade_item: Dict):
        pass

    def parse_trading_elements(self, trading_elements_list: list) -> List:
        pass

    def trade_history(self, code: str, size: int = 20, page: int = 1) -> List:
        """
        获取组合的调仓历史，数据库初始化组合时调用该接口
        :param page:
        :param size:
        :param code:
        :return:
        """
        pass

    def pagination_trade_info(self, code: str, size: int = 20) -> List:
        """
        翻页查询
        """
        pass

    def parse_net_worth(self, code: str, size: int = 30, page: int = 1):
        pass

    def net_worth(self, code: str, size: int = 30, is_df=True) -> List:
        pass


if __name__ == '__main__':
    s = Strategy()
    ret = s.detail()
    print(ret)

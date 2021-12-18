#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/16 11:09
@file: combination.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 爬取蛋卷基金的基金组合并保存到数据库，为后期跟踪策略提供数据
"""
import math
from typing import Dict, List, Optional

import pandas as pd
from xalpha.cons import rget_json

from backend.fundmate.libs import convert


class Strategy:
    """
    以银行螺丝钉为例
    https://danjuanapp.com/strategy/CSI1033
    """

    def get(self):
        """获取所有组合"""
        pass

    def is_success(self, response: dict) -> bool:
        return response and response.get('result_code') == 0

    def detail(self, code: str) -> Optional[Dict]:
        """
        获取单个组合的信息
        :param code:
        :return:
        """
        _url = f'https://danjuanapp.com/djapi/plan/{code}'
        _resp = rget_json(_url)
        if self.is_success(_resp):
            data = _resp.get('data')
            if data:
                plan_name = data.get('plan_name')
                plan_code = data.get('plan_code')
                found_date = data.get('found_date')
                plan_type = data.get('type')
                manager_name = data.get('manager_name')
                manager_profile_photo = data.get('manager_profile_photo')
                invest_money_type = data.get('invest_money_type')  # 资金维度  ：积极增值
                invest_time_type = data.get('invest_time_type')  # 时间纬度：持有3年以上
                last_trade_date_fmt = data.get('last_trade_date_fmt')
                # 费率信息（暂不需要）
                # plan_rates = data.get('plan_rates')
                return {
                    'plan_code': plan_code,
                    'plan_name': plan_name,
                    'plan_type': plan_type,
                    'found_date': found_date,
                    'manager_name': manager_name,
                    'manager_profile_photo': manager_profile_photo,
                    'invest_money_type': invest_money_type,
                    'invest_time_type': invest_time_type,
                    'last_trade_date_fmt': last_trade_date_fmt,
                }
        return None

    def total_times(self, plan_code: str) -> Optional[int]:
        """
        调仓总次数
        作为判断是否需要更新的依据
        :param plan_code:
        :return:
        """
        params = {'plan_code': plan_code}
        _url = 'https://danjuanapp.com/djapi/fundx/portfolio/plan/plan_summery'
        resp = rget_json(_url, params=params)
        if self.is_success(resp):
            data = resp.get('data')
            total_time = data.get('total_time')
            return int(total_time)
        return None

    def per_trading_remark(self, trade_item: Dict):
        """
        调仓说明
        :param trade_item:
        :return:
        """
        remark = trade_item.get('remark')
        return remark

    def parse_trading_elements(self, trading_elements_list: list) -> List:
        trade_list = list()
        for trading_element in trading_elements_list:
            fd_code = trading_element.get('fd_code')
            portion = trading_element.get('portion')
            elem = {'fd_code': fd_code, 'portion': float(portion)}
            trade_list.append(elem)
        return trade_list

    def trade_history(self, code: str, size: int = 20, page: int = 1) -> List:
        """
        获取组合的调仓历史，数据库初始化组合时调用该接口
        :param page:
        :param size:
        :param code:
        :return:
        """
        _url = f'https://danjuanapp.com/djapi/plan/{code}/trade_history'
        params = {'size': size, 'page': page}
        resp = rget_json(_url, params=params)
        if self.is_success(resp):
            data = resp.get('data')
            per_trading_detail = data.get('items')
            page_items = list()
            for items in per_trading_detail:
                remark = self.per_trading_remark(items)
                trade_id = items.get('trading_id')  # 标记，不存入数据库
                trade_date = items.get('trade_date')
                trading_elements_list = items.get('trading_elements')
                trading_elements = self.parse_trading_elements(trading_elements_list)
                iso_date = convert.try_parse_date(str(trade_date)).strftime("%Y-%m-%d")
                # 单次调仓信息
                trade_detail = {
                    'trading_id': trade_id,
                    'trade_date': iso_date,
                    'remark': remark,
                    'trading_elements': trading_elements,
                }
                page_items.append(trade_detail)
            return page_items

    def pagination_trade_info(self, code: str, size: int = 20) -> List:
        """
        翻页查询
        """
        _total_times = self.total_times(code)
        raw_total_pages = _total_times / size
        total_pages = math.ceil(raw_total_pages)

        trade_info = list()
        for page_num in range(1, total_pages + 1):
            per_page_trade_history = self.trade_history(code, size, page_num)
            if per_page_trade_history:
                trade_info.extend(per_page_trade_history)
        return trade_info

    def parse_net_worth(self, code: str, size: int = 30, page: int = 1):
        _url = f'https://danjuanapp.com/djapi/plan/nav/history/{code}'
        params = {'size': size, 'page': page}
        resp = rget_json(_url, params=params)
        if self.is_success(resp):
            data = resp.get('data')
            item = data.get('items')
            return item

    def net_worth(self, code: str, size: int = 30, is_df=True) -> List:
        """
        网页参考：https://danjuanapp.com/net-performance/CSI1033
        获取组合的历史净值
        :param size:
        :param code:
        :param is_df:
        :return:
        """
        _url = f'https://danjuanapp.com/djapi/plan/nav/history/{code}'
        params = {'size': size}
        resp = rget_json(_url, params=params)

        if self.is_success(resp):
            data = resp.get('data')
            total_pages = int(data.get('total_pages'))
            first_page_item = data.get('items')
            first_page_df = pd.DataFrame(first_page_item)
            ept_df = pd.DataFrame([])
            df = pd.concat([ept_df, first_page_df])
            # 第一页已经查出来了，没有必要重复请求了
            for page_num in range(2, total_pages + 1):
                per_page_items = self.parse_net_worth(code, size, page_num)
                if per_page_items:
                    df_item = pd.DataFrame(per_page_items)
                    df = pd.concat([df, df_item]).reset_index(drop=True)
            useful_data_df = df[['date', 'value']]
            if not is_df:  # 往数据库中存的话，没有必要转换
                ret_data = useful_data_df.to_dict(orient='records')
                return ret_data
            return useful_data_df


if __name__ == '__main__':
    s = Strategy()
    ret = s.pagination_trade_info('CSI1032')
    net_val = s.net_worth('CSI1032')
    print(net_val)

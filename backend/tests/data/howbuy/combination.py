#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/16 11:09
@file: combination.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 爬取好买基金的基金组合（牛基宝）并保存到数据库，为后期跟踪策略提供数据
"""
from typing import Dict, List, Optional

import pandas as pd
from xalpha.cons import rget_json

from backend.fundmate.excepts import LenEqualError
from backend.fundmate.libs import convert


class Strategy:
    """
    以牛基宝（全股型）为例：
    https://trade.ehowbuy.com/newpig/index.html#/adviser/index?productCode=tzzhqgx
    """

    def __init__(self):
        self.base_url = 'https://data.howbuy.com/cgi/fund/'
        self.history_url = self.base_url + 'v731z/clcplsgd.json'
        self.net_worth_url = self.base_url + 'v717z/clcplshb.json'

    def list_all(self) -> Optional[List]:
        """获取所有组合"""
        api = 'v640/getcmsrecommed.json?key=tzzhday'
        url = self.base_url + api
        resp = rget_json(url)
        if self.is_success(resp):
            results = resp.get('body').get('column')
            poi_df = pd.DataFrame(results)
            usable_info = poi_df[["columnId", "name", "description", "id", "urlLink"]]
            portfolios = usable_info.to_dict(orient='records')
            return portfolios

    def is_success(self, response: dict) -> bool:
        return response and response.get('code') == '0000'

    def detail(self, code: str, plan_name: str, plan_desc: str) -> Optional[Dict]:
        """
        获取单个组合的信息
        单次调仓时通过该接口获取即可
        :param plan_desc:
        :param plan_name:
        :param code:
        :return:
        """
        _url = f'v717z/clcpday.json?zhdm={code}'
        _resp = rget_json(_url)
        if self.is_success(_resp):
            body = _resp.get('body')
            period_detail = body.get('jdpbmx')  # 阶段配比明细
            manager = body.get('zlr')  # 主理人
            mgr_info = {
                'plat_code': None,
                'name': manager.get('name'),
                'mgr_avatar_url': manager.get('picUrl'),
            }
            choice_fund_pools = body.get('bxjjk')  # 备选基金库
            base_info = body.get('jbxx')  # 基本信息
            return_info = body.get('syxx')  # 收益信息
            if base_info:
                # plan_name = data.get('plan_name')
                # plan_code = data.get('plan_code')
                found_date = return_info.get('cjrq')  # 创建日期
                annualized_rate_of_return = return_info.get('nhhbcl')
                invest_rate_of_return = return_info.get('hbcl')
                # max_down_return = return_info.get('zdhccl')  # 最大回撤
                # plan_desc_info = data.get('plan_desc')[-1]
                # plan_desc = plan_desc_info.get('plan_desc')
                last_trade_date_fmt = period_detail.get('zhsjrq')
                trading_elements_list = period_detail.get('fundList')
                trading_elements = self.parse_trading_elements(trading_elements_list)
                # 费率信息（暂不需要）
                # plan_rates = data.get('plan_rates')
                return {
                    'code': code,
                    'name': plan_name,
                    'risk_type': None,
                    'found_date': found_date,
                    'annualized_rate_of_return': annualized_rate_of_return,
                    'invest_rate_of_return': invest_rate_of_return,
                    'desc': plan_desc,
                    'mgr_info': mgr_info,
                    'last_adjust_date': last_trade_date_fmt,
                    'choice_fund_pools': choice_fund_pools,
                    'last_trading_elements': trading_elements,
                }
        return None

    def parse_trading_elements(self, trading_elements_list: list) -> List:
        """
        每一次调仓成分基金的解析
        :param trading_elements_list:
        :return:
        """
        trade_list = list()
        for trading_element in trading_elements_list:
            fd_code = trading_element.get('jjdm')
            portion = trading_element.get('cczb')  # 资产占比
            elem = {'fd_code': fd_code, 'portion': float(portion)}
            trade_list.append(elem)
        return trade_list

    def parse_page_data(self, per_page_data):
        """
        每页的调仓信息，即n次调仓记录的详情信息
        :param per_page_data:
        :return:
        """
        per_trading_detail = per_page_data.get('dataList')
        page_items = list()
        for items in per_trading_detail:
            remark = items.get('ms1')
            trade_date = items.get('gdqsrq')
            trading_elements_list = items.get('fundList')
            trading_elements = self.parse_trading_elements(trading_elements_list)
            iso_date = self.datestr_to_isodatestr(trade_date)
            # 单次调仓信息
            trade_detail = {
                'trading_id': trade_date,
                'trade_date': iso_date,
                'remark': remark,
                'trading_elements': trading_elements,
            }
            page_items.append(trade_detail)
        return page_items

    def trade_history(self, code: str, page: int = 1) -> List:
        """
        获取组合的调仓历史，数据库初始化组合时调用该接口
        :param page:
        :param size:
        :param code:
        :return:
        """
        params = {'zhdm': code, 'current': page}
        resp = rget_json(self.history_url, params=params)
        if self.is_success(resp):
            data = resp.get('body')
            page_items = self.parse_page_data(data)
            return page_items

    def pagination_trade_info(self, code: str) -> List:
        """
        翻页查询，获取所有调仓信息
        原始网页：
        https://trade.ehowbuy.com/newpig/index.html#/adviser/adjustRecord?investmentAdviser=0&productCode=tzzhqgx&isHistory=1?corpId=&coopId=&HBTag=
        """
        params = {'zhdm': code, 'current': 1}
        resp = rget_json(self.history_url, params=params)
        if self.is_success(resp):
            data = resp.get('body')
            total = int(data.get('total'))
            total_pages = int(data.get('pages'))
            trade_info = list()
            # 第一次请求的即为最新的消息
            first_page_items = self.parse_page_data(data)
            trade_info.extend(first_page_items)

            for page_num in range(2, total_pages + 1):
                per_page_trade_history = self.trade_history(code, page_num)
                if per_page_trade_history:
                    trade_info.extend(per_page_trade_history)
            if total != len(trade_info):
                raise LenEqualError('返回数据长度与接口总量不一致！')
            return trade_info

    def parse_net_worth(self, code: str, size: int = 30, page: int = 1):
        params = {'zhdm': code, 'current': page, 'size': size}
        resp = rget_json(self.net_worth_url, params=params)
        if self.is_success(resp):
            data = resp.get('body')
            item = data.get('dataList')
            return item

    def datestr_to_isodatestr(self, str_date: str):
        """
        >>> datestr_to_isodatestr('20220104')
        >>> '2022-01-04'
        :param str_date:
        :return:
        """
        datetime_str = str(pd.to_datetime(str_date))
        iso_date = str(convert.try_parse_date(datetime_str))
        return iso_date

    def net_worth(self, code: str, size: int = 50, is_df=True) -> Optional[List]:
        """
        原始网页：https://trade.ehowbuy.com/newpig/index.html#/adviser/adviserJzZf
        ?productCode=tzzhqgx&isHbyj=0&lssy=2&corpId=&coopId=&HBTag=
        获取组合的历史回报
        :param size:
        :param code:
        :param is_df:
        :return:
        """
        params = {'zhdm': code, 'current': 1, 'size': size}
        resp = rget_json(self.net_worth_url, params=params)

        if self.is_success(resp):
            data = resp.get('body')
            total = int(data.get('total'))
            pages = int(data.get('pages'))
            first_page_item = data.get('dataList')
            first_page_df = pd.DataFrame(first_page_item)
            ept_df = pd.DataFrame([])
            df = pd.concat([ept_df, first_page_df])
            # 第一页已经查出来了，没有必要重复请求了
            for page_num in range(2, pages + 1):
                per_page_items = self.parse_net_worth(code, size, page_num)
                if per_page_items:
                    df_item = pd.DataFrame(per_page_items)
                    df = pd.concat([df, df_item]).reset_index(drop=True)
            useful_data_df = df[['zhjz', 'jzrq']]  # 组合净值 截止日期
            useful_data_df.columns = ['value', 'date']
            useful_data_df['date'] = useful_data_df.date.apply(lambda x: self.datestr_to_isodatestr(x))
            if total != len(useful_data_df):
                raise LenEqualError('返回数据长度与接口总量不一致！')
            # 只获取交易日的净值存入（其他没意义）
            useful_data_df = useful_data_df[useful_data_df.jyr == '1']
            if not is_df:  # 往数据库中存的话，没有必要转换
                ret_data = useful_data_df.to_dict(orient='records')
                return ret_data
            return useful_data_df


if __name__ == '__main__':
    s = Strategy()
    code = 'tzzhqgx'
    ret = s.pagination_trade_info(code)
    print(ret)
    net_val = s.net_worth(code)
    print(net_val)
    detail = s.detail(code)
    print(detail)

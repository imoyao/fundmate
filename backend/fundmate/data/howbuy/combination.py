#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/16 11:09
@file: combination.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 爬取好买基金的基金组合（牛基宝）并保存到数据库，为后期跟踪策略提供数据
# TODO: 目前信息中的 float(x)/100 返回值导致精度不正确，需要处理

策略地址：https://trade.ehowbuy.com/newpig/index.html#/adviser/index?productCode={{code}}
"""
import math
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
        self.over_view_url = self.base_url + 'v717z/clcpday.json'
        self.indicator_url = self.base_url + 'v717z/clcphbzst.json'
        self.zo_all_star = {
            'name': '超级股票全明星',
            'description': '超级股票全明星以过往长期业绩优秀的基金为核心基础配置，动态配置大小盘、行业风格的“卫星”基金。多元配置，分散风险，力争在不同市场周期下赚取超额回报。',
            'urlLink': 'zozh002'
        }

    def list_all(self) -> Optional[Dict]:
        """获取所有组合"""
        api = 'v640/getcmsrecommed.json?key=tzzhday'
        url = self.base_url + api
        resp = rget_json(url)
        if self.is_success(resp):
            results = resp.get('body').get('column')
            poi_df = pd.DataFrame(results)
            # usable_info = poi_df[['columnId', 'name', 'description', 'id', 'urlLink']]
            usable_info = poi_df[['name', 'description', 'urlLink']]
            portfolios = usable_info.to_dict(orient='records')
            portfolios.append(self.zo_all_star)

            portfolios_dict = {item.get('urlLink'): item for item in portfolios}
            return portfolios_dict

    def is_success(self, response: dict) -> bool:
        return response and response.get('code') == '0000'

    def get_choice_fund_pools(self, code: str):
        """
        获取组合的备选基金池
        :param code:
        :return:
        """
        params = {'zhdm': code}
        _resp = rget_json(self.over_view_url, params=params)
        if self.is_success(_resp):
            body = _resp.get('body')
            choice_fund_pools_raw = body.get('bxjjk')  # 备选基金库
            choice_fund_pools_fund_lists = choice_fund_pools_raw.get('dataList')
            choice_fund_pools = [fund.get('jjdm') for fund in choice_fund_pools_fund_lists]
            return choice_fund_pools

    def newest_holds(self, code: str):
        """
        最新持仓
        **注意** 这个里面的日期数据是不准确的
        :param code:
        :return:
        """
        params = {'zhdm': code}
        _resp = rget_json(self.over_view_url, params=params)
        if self.is_success(_resp):
            body = _resp.get('body')
            period_detail = body.get('jdpbmx')  # 阶段配比明细
            trading_elements_list = period_detail.get('fundList')
            last_trading_elements = self.parse_trading_elements(trading_elements_list)
            return last_trading_elements

    def indicator(self, code: str) -> Optional[Dict]:
        """
        指标分析
        :return:
        """

        def _ret_val(info):
            return info.get('sz1')

        params = {'zhdm': code, 'range': '1N'}
        _resp = rget_json(self.indicator_url, params=params)
        if self.is_success(_resp):
            data = _resp.get('body')
            raw_indicator_list = data.get('qjzb').get('dataList')
            if raw_indicator_list:
                _, volatility_info, sharpe_info, max_drawdown_info = raw_indicator_list
                max_drawdown = _ret_val(max_drawdown_info)
                sharpe = _ret_val(sharpe_info)
                volatility = _ret_val(volatility_info)

                return {
                    'max_drawdown': float(max_drawdown) / 100,
                    'sharpe': sharpe,
                    'volatility': float(volatility) / 100,
                }

    def detail(self, code: str) -> Optional[Dict]:
        """
        获取单个组合的信息
        单次调仓时通过该接口获取即可
        :param plan_desc:
        :param plan_name:
        :param code:
        :return:
        """
        _all_pois = self.list_all()
        poi_info = _all_pois.get(code)
        plan_name = poi_info.get('name')
        plan_desc = poi_info.get('description')
        params = {'zhdm': code}
        _resp = rget_json(self.over_view_url, params=params)

        if self.is_success(_resp):
            body = _resp.get('body')
            manager = body.get('zlr')  # 主理人
            plan_rich_desc = body.get('cpjs').get('recommendReason')  # 产品介绍 推荐理由
            mgr_info = {
                'plat_code': None,
                'name': manager.get('name'),
                'mgr_avatar_url': manager.get('picUrl'),
                'desc': manager.get('recommendReason', None),
            }

            base_info = body.get('jbxx')  # 基本信息
            return_info = body.get('syxx')  # 收益信息
            if base_info:
                raw_found_date = return_info.get('cjrq')  # 创建日期
                found_date = self.datestr_to_isodatestr(raw_found_date)
                annualized_rate_of_return = return_info.get('nhhbcl')
                invest_rate_of_return = return_info.get('hbcl')  # 回报
                # max_drawdown = return_info.get('zdhccl')
                last_raw_date = base_info.get('zhsjrq')
                if last_raw_date:
                    last_trade_date_fmt = self.datestr_to_isodatestr(last_raw_date)
                else:
                    period_detail = body.get('zxgd')  # 最新gd：归档？
                    last_raw_date = period_detail.get('gdqsrq')
                    last_trade_date_fmt = self.datestr_to_isodatestr(last_raw_date)
                indicator_info = self.indicator(code)
                info = {
                    'code': code,
                    'name': plan_name,
                    'risk_type': None,
                    'found_date': found_date,
                    'annualized_rate_of_return': annualized_rate_of_return if annualized_rate_of_return else 0,
                    'invest_rate_of_return': invest_rate_of_return,
                    'desc': plan_desc,
                    'rich_desc': plan_rich_desc,
                    'mgr_info': mgr_info,
                    'indicator': indicator_info,
                    'last_adjust_date': last_trade_date_fmt,
                }
                return info
        return None

    def parse_trading_elements(self, trading_elements_list: list) -> List:
        """
        对每一次调仓成分基金进行解析
        :param trading_elements_list:
        :return:
        """
        trade_list = list()
        if trading_elements_list is not None:
            for trading_element in trading_elements_list:
                fd_code = trading_element.get('jjdm')
                portion = trading_element.get('cczb')  # 资产占比必须转为小数
                elem = {'fd_code': fd_code, 'portion': float(portion) / 100}
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

    def get_last_adjust_date(self, code: str) -> Optional[str]:
        """
        获取组合最后一次调仓真实日期
        :param code:
        :return:
        """
        params = {'zhdm': code}
        _resp = rget_json(self.over_view_url, params=params)

        if self.is_success(_resp):
            body = _resp.get('body')
            base_info = body.get('jbxx')  # 基本信息
            last_raw_date = base_info.get('zhsjrq')
            if last_raw_date:
                last_trade_date_fmt = self.datestr_to_isodatestr(last_raw_date)
            else:
                period_detail = body.get('zxgd')  # 最新gd：归档？
                last_raw_date = period_detail.get('gdqsrq')
                last_trade_date_fmt = self.datestr_to_isodatestr(last_raw_date)
            return last_trade_date_fmt

    def trade_history(self, code: str, size: int = 10, page: int = 1) -> List:
        """
        获取组合的调仓历史，数据库初始化组合时调用该接口
        :param page:
        :param size:
        :param code:
        :return:
        """
        params = {'zhdm': code, 'current': page, 'size': size}
        resp = rget_json(self.history_url, params=params)
        if self.is_success(resp):
            data = resp.get('body')
            page_items = self.parse_page_data(data)
            return page_items

    def total_times(self, code):
        """
        调仓总次数
        :param code:
        :return:
        """
        params = {'zhdm': code, 'current': 1}
        resp = rget_json(self.history_url, params=params)
        if self.is_success(resp):
            data = resp.get('body')
            total = int(data.get('total'))
            return total

    def pagination_trade_info(self, code: str, size: int = 10, is_desc: bool = True) -> List:
        """
        翻页查询，获取所有调仓信息

        原始网页：
        https://trade.ehowbuy.com/newpig/index.html#/adviser/adjustRecord?investmentAdviser=0&productCode=tzzhqgx&isHistory=1?corpId=&coopId=&HBTag=
        :param code:
        :param size:
        :param is_desc: 默认最新的在最前；只有当获取完整列表时注意，在更新操作时，必须保证为True，否则排在最前面的不是最新持仓
        :return:
        """
        params = {'zhdm': code, 'size': size, 'current': 1}
        resp = rget_json(self.history_url, params=params)
        if self.is_success(resp):
            data = resp.get('body')
            total = int(data.get('total'))
            total_pages = math.ceil(total / size)
            trade_info = list()
            # 第一次请求的即为最新的消息
            first_page_items = self.parse_page_data(data)
            trade_info.extend(first_page_items)
            if size > 10:
                for page_num in range(2, total_pages + 1):
                    per_page_trade_history = self.trade_history(code, size, page_num)
                    if per_page_trade_history:
                        trade_info.extend(per_page_trade_history)
                # 请求size条时，不需要判断total是否等于总的条数
                if total != len(trade_info):
                    raise LenEqualError('返回数据长度与接口总量不一致！')
            if not is_desc:
                # 最旧的排在最前面
                trade_info = trade_info[::-1]
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
        >>> stg = Strategy()
        >>> stg.datestr_to_isodatestr('20220104')
        '2022-01-04'

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
            useful_data_df = df[['zhjz', 'jzrq', 'jyr']]  # 组合净值 截止日期
            useful_data_df.columns = ['value', 'date', 'is_trade_day']
            useful_data_df['date'] = useful_data_df.date.apply(lambda x: self.datestr_to_isodatestr(x))
            if total != len(useful_data_df):
                raise LenEqualError('返回数据长度与接口总量不一致！')
            # 只获取交易日的净值存入（其他没意义）
            useful_data_df = useful_data_df[useful_data_df.is_trade_day == '1']
            return_df = useful_data_df[['value', 'date']]
            if not is_df:  # 往数据库中存的话，没有必要转换
                ret_data = return_df.to_dict(orient='records')
                return ret_data
            return return_df


if __name__ == '__main__':
    s = Strategy()
    # 所有待抓取的组合
    all_pois = s.list_all()
    print(all_pois)
    code = 'zozh002'
    # 备选基金池
    result = s.get_choice_fund_pools(code)
    print(result)
    # 最新持仓
    newest_holds = s.newest_holds(code)
    print(newest_holds)
    # 所有持仓信息
    ret = s.pagination_trade_info(code)
    print(ret)
    # 净值信息
    net_val = s.net_worth(code)
    print(net_val)
    # 组合详情信息
    detail = s.detail(code)
    print(detail)
    # 技术指标
    ret = s.indicator(code)
    print(ret)

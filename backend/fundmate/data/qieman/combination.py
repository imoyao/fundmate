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
from typing import Dict, List, Optional, Union

import pandas as pd
from xalpha.cons import rget_json

from backend.fundmate.data.qieman import utils
from backend.fundmate.libs import convert

PdDataFrame = pd.DataFrame


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

    def list_all(self):
        """获取所有组合
        目前手动写死
        '''
        参考来源：
        1. [一石二鸟 - 且慢](https://qieman.com/portfolios/manager/201121)
        2. [更多投资选择](https://qieman.com/m4/more)
        '''
        """
        portfolios = [
            'ZH030684',
            'ZH043108',
            'ZH035411',
            'ZH032680',
            'ZH013136',
            'ZH000082',
            'ZH010292',
            'ZH000129',
            'ZH006498',
            'ZH012926',
            'ZH039784',
            'ZH000193',
            'ZH036560',
            'ZH041288',
        ]
        return portfolios

    def get_last_adjust_date(self, code: str) -> Optional[str]:
        url = f'https://qieman.com/pmdj/v1/pomodels/{code}'
        resp = rget_json(url, headers=self.headers)
        if resp:
            adjust_info = resp.get('adjustInfo')
            last_trade_date_fmt = adjust_info.get('adjustedOn')
            return last_trade_date_fmt

    def detail(self, code: str = 'ZH000001') -> Optional[Dict]:
        """
        获取单个组合的信息
        :param code:
        :return:
        """
        url = f'https://qieman.com/pmdj/v1/pomodels/{code}'
        resp = rget_json(url, headers=self.headers)
        if resp:
            plan_name = resp.get('poName')
            plan_code = resp.get('poCode')
            found_date = resp.get('establishedOn')
            plan_type = resp.get('risk5Level')
            plan_desc = resp.get('poDesc')
            plan_rich_desc = resp.get('poRichDesc')
            invest_rate_of_return = resp.get('fromSetupReturn')
            annualized_rate_of_return = resp.get('annualCompoundedReturn')
            mgr_infos = resp.get('poManagers')[0]
            mgr_name = ''
            mgr_avatar = ''
            mgr_code = ''
            mgr_desc = ''
            # is_verified = False
            if mgr_infos:
                mgr_name = mgr_infos.get('poManagerName')
                mgr_avatar = mgr_infos.get('poManagerAvatarUrl')
                mgr_code = mgr_infos.get('poManagerId')
                mgr_desc = mgr_infos.get('poManagerDesc')
                # is_verified = mgr_infos.get('verified')  # 认证用户
            adjust_info = resp.get('adjustInfo')
            last_trade_date_fmt = adjust_info.get('adjustedOn')
            mgr_info = {
                'plat_code': mgr_code,
                'name': mgr_name,
                'mgr_avatar_url': mgr_avatar,
                'desc': mgr_desc,
            }
            return {
                'code': plan_code,
                'name': plan_name,
                'risk_type': plan_type,
                'found_date': found_date,
                'annualized_rate_of_return': annualized_rate_of_return,
                'invest_rate_of_return': invest_rate_of_return,
                # 'is_verified': is_verified,
                'desc': plan_desc,
                'mgr_info': mgr_info,
                'rich_desc': plan_rich_desc,
                # 'invest_money_type': '',
                # 'invest_time_type': invest_time_type,
                'last_adjust_date': last_trade_date_fmt,
            }

        return resp

    def parse_trading_elements(self, trading_elements_list: list, is_df: bool = False) -> Union[List, PdDataFrame]:
        """
        每一次调仓成分基金的解析
        :param is_df:
        :param trading_elements_list:
        :return:
        """
        trade_list = list()
        for trading_element in trading_elements_list:
            fd_code = trading_element.get('fundCode')
            portion = trading_element.get('toPercent')
            elem = {'fd_code': fd_code, 'portion': float(portion)}
            trade_list.append(elem)
        if is_df:
            trade_df = pd.DataFrame(trade_list)
            return trade_df
        return trade_list

    def trade_history(self, trading_history: List) -> List:
        """
        获取组合的调仓历史，数据库初始化组合时调用该接口
        :param trading_history:
        :return:
        """
        page_items = list()
        for per_trading_detail in trading_history:
            trade_id = per_trading_detail.get('adjustmentId')
            trade_date = per_trading_detail.get('adjustedOn')
            remark = per_trading_detail.get('comment')
            details = per_trading_detail.get('details')
            trading_elements = self.parse_trading_elements(details)
            trade_detail = {
                'trading_id': trade_id,
                'trade_date': trade_date,
                'remark': remark,
                'trading_elements': trading_elements,
            }
            page_items.append(trade_detail)
        return page_items

    def adjustments(self,
                    code: str,
                    page: int = 0,
                    size: int = 20,
                    format_type: str = 'openapi',
                    is_desc: bool = True) -> Optional[Dict]:
        """
        获取调仓概览信息
        :param code:
        :param page:
        :param size:
        :param format_type:
        :param is_desc:
        :return:
        """
        _url = f'https://qieman.com/pmdj/v1/pomodels/{code}/adjustments'
        params = {'page': page, 'size': size, 'format': format_type, 'isDesc': is_desc}
        resp = rget_json(_url, headers=self.headers, params=params)
        if resp:
            total_pages = resp.get('totalPages')
            content = resp.get('content')
            total_count = resp.get('totalElements')
            el_size = resp.get('size')
            return {
                'total': total_count,
                'total_page': total_pages,
                'content': content,
                'size': el_size,
            }

    def pagination_trade_info(self,
                              code: str,
                              page: int = 0,
                              size: int = 20,
                              format_type: str = 'openapi',
                              is_desc: bool = True) -> List:
        """
        翻页查询调仓历史
        """
        _url = f'https://qieman.com/pmdj/v1/pomodels/{code}/adjustments'
        adjustments_info = self.adjustments(code, page=page, size=size, format_type=format_type, is_desc=is_desc)
        content = adjustments_info.get('content')
        total_pages = adjustments_info.get('total_page')
        trade_info = list()
        per_page_content = self.trade_history(content)
        trade_info.extend(per_page_content)
        for page_num in range(1, int(total_pages) + 1):
            params = {'page': page_num, 'size': size, 'format': format_type, 'isDesc': is_desc}
            resp = rget_json(_url, headers=self.headers, params=params)
            if resp:
                content = resp.get('content')
                per_page_content = self.trade_history(content)
                trade_info.extend(per_page_content)
        return trade_info

    def net_worth(self, code: str, is_df=True, is_desc=True) -> Union[List, PdDataFrame]:
        """
        获取组合的历史净值
        :param code:
        :param is_df:
        :param is_desc:
        :return:
        """
        _url = f'https://qieman.com/pmdj/v1/pomodels/{code}/nav-history'
        resp = rget_json(_url, headers=self.headers)
        if resp:
            ret_df = pd.DataFrame(resp)
            useful_data_df = ret_df[['navDate', 'nav']]
            rename_df = useful_data_df.rename(columns={'navDate': 'date', 'nav': 'value'})
            rename_df['date'] = rename_df.date.apply(lambda x: convert.try_parse_date(str(x)).strftime("%Y-%m-%d"))
            if is_desc:
                rename_df = rename_df.iloc[::-1].reset_index(drop=True)
            if not is_df:  # 往数据库中存的话，没有必要转换，使用dataframe更好
                ret_data = rename_df.to_dict(orient='records')
                return ret_data
            return rename_df


if __name__ == '__main__':
    s = Strategy()
    code = 'ZH039784'
    ret = s.net_worth(code)
    print(ret)
    result = s.pagination_trade_info(code)
    print(result)
    po_detail = s.detail(code)
    print(po_detail)

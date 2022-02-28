#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/6/8 17:40
"""
https://www.jisilu.cn/question/abstract/310234#!answer_3709513
具体指标查询网址
TTM等权市盈率：https://legulegu.com/stockdata/a-ttm-lyr
股债利差：https://danjuanapp.com/valuation-table/jiucai
螺丝钉指数估值表：https://danjuanfunds.com/screw/valuation-table?channel=1500012085
集思录温度计：https://www.jisilu.cn/data/indicator/
有知有行温度计：https://youzhiyouxing.cn/thermometer
"""
from typing import Dict, List, Optional, Union

import cachetools.func
import pandas as pd
import portion
from xalpha.cons import rget_json

from backend.fundmate import utils
from backend.fundmate.data.utils import base as dt_utils
from backend.fundmate.data.utils import ratio
from backend.fundmate.exts.flask_loguru import logger

header_str = '''Accept: application/json, text/plain, */*
Accept-Encoding: gzip, deflate, br
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7
Connection: keep-alive
Cookie: device_id=web_H1rTlL64qu; xq_a_token=aa8cf5aa25e1e9dd1cb237236a8bec27242760bf;''' \
             '''Hm_lvt_d8a99640d3ba3fdec41370651ce9b2ac=1622623735,1622625108,1623045004;''' \
             '''acw_tc=2760778916231451543431366e8e1c2515e2724de5101def82af28c6d920e0;''' \
             '''channel=1500012085; Hm_lpvt_d8a99640d3ba3fdec41370651ce9b2ac=1623145825;''' \
             ''' timestamp=1623145824959
DNT: 1
elastic-apm-traceparent: 00-dd761310377a09f702d0df61ae45900c-ed908de0729027eb-01
Host: danjuanfunds.com
Referer: https://danjuanfunds.com/screw/valuation-table?channel=1500012085
sec-ch-ua: " Not;A Brand";v="99", "Microsoft Edge";v="91", "Chromium";v="91"
sec-ch-ua-mobile: ?0
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ''' \
             '''Chrome/91.0.4472.77 Safari/537.36 Edg/91.0.864.41
'''  # noqa: F501


class DanJuanEvl:
    """
    估值信息
    lsd: {"lsd": {
            "data": {
                "id": 4667,
                "periods": "1676",
                "status": "1",
                "time": "2021-06-08",
                "comment": "高筑墙 广积粮 缓称王",
                "grade": "3",
                "valuations": [{
                    "dividend_yield": 0.0313,   # 股息率
                    "id": 21996,
                    "index_code": "000919",
                    "index_name": "300价值",
                    "outside_fund": "519671",   # 场外基金
                    "pb": 1.03,                 # 市净率
                    "pe": 9.95,                 # 市盈率
                    "profit_yield": 0.1005,     # 盈利收益率
                    "relation_id": 4675,
                    "roe": 0.1031,              # ROE
                    "valuation_status": "1"     # 估值状态（越小投资价值越大）
                },
                ...]
            },
            "result_code": 0
        }}

    主要关注投资星级：1星为泡沫阶段，5星为投资价值最高阶段。
    ---
    [A股估值方法的详细说明](https://mp.weixin.qq.com/s/E4Ne_OfsRRjUBK9vWL2ABg)

    股债利差就是：用股票预期收益率减去十年国债收益率得到的差值（股票 - 债券）。

    数值越大代表此时买股票性价比越高于买债券。

    绿色:估值较低，适合定投
    黄色:估值正常，可以观望
    红色:估值较高，谨慎投资


    通常认为股债利差>3时，市场股票低估适合买入。
    jiucai： {"jiucai": {
        "data": {
            "id": 4665,
            "periods": "644",
            "status": "1",
            "time": "2021-06-08",
            "comment": "A股整体估值偏低",
            "spread_td": 0.0244,  # 股债利差
            "valuations": [{"crowding_degree": 0.045,   # 拥挤度
                            "id": 22025,
                            "index_code": "399905",     # 指数编码
                            "index_name": "中证500",     # 指数名称
                            "index_type": "宽基指数",    # 指数类型
                            "inside_fund": "510500",    # 场内基金编号
                            "outside_fund": "510500",   # 场外基金编号
                            "pb": 2.15,                 # PB 市净率
                            "pb_percent": 0.285,        # PB百分位
                            "pe": 25.55,                # PE市盈率
                            "relation_id": 4676,        
                            "valuation_status": "1"     # 估值状态（越小投资价值越大）
                            },...],
            "ashares_total_percent": 0.519  # A股整体估值分位
        },
        "result_code": 0
    }}

    """

    CHANNEL_LIST = ['jiucai', 'lsd']

    def get_detail(self, channel: Union[str, None] = None) -> dict:
        """
        实际爬取函数的封装
        :param channel:订阅的数据源，现在支持 韭菜 和 螺丝钉
        :return:
        """
        assert channel in self.CHANNEL_LIST
        url = f'https://danjuanapp.com/djapi/fundx/activity/user/vip_valuation/show/detail?source={channel}'
        hd = dt_utils.parse_headers(header_str)
        resp = rget_json(url, headers=hd)
        return resp

    def eval_val(self, is_full: bool = False) -> dict:
        """
        抓取信息
        :return:
        """
        info = dict()
        for channel in self.CHANNEL_LIST:
            item = self.get_detail(channel)

            data = item.get('data')
            data.pop('spread_trends')
            href = ''
            if channel == 'lsd':
                href = 'https://danjuanfunds.com/screw/valuation-table?channel=1500012085'
            elif channel == 'jiucai':
                href = 'https://danjuanapp.com/valuation-table/jiucai'

            data['href'] = href
            if is_full:
                item['data'] = data
            else:
                _time = data.get('time')
                desc = data.get('comment')
                item_data = {'date': _time, 'comment': desc}
                point = dict()
                if channel == 'lsd':
                    grade = data.get('grade')
                    point = {'grade': grade, 'href': href}
                elif channel == 'jiucai':
                    spread_td = data.get('spread_td')
                    point = {'spread_td': spread_td, 'href': href}

                item_data.update(point)

                item['data'] = item_data

            info[channel] = item
        return info

    @cachetools.func.ttl_cache(maxsize=128, ttl=utils.seconds_today_leaves())
    def valuation(self, is_full: bool = False) -> dict:
        """
        只显示概要信息
        :return:
        """
        _info = self.eval_val(is_full=is_full)
        return _info


class FundFeeRatio(ratio.BaseRatio):
    """
    蛋卷基金费率信息获取
    """

    def fund_detail(self, fund_code: str) -> Union[dict, None]:
        """
        基金详情信息，包含费率和季度报信息
        ref: https://danjuanapp.com/funding/001714/rate
        :param fund_code:
        :return: 基金持仓和费率，like this:
        ```
                {
            'position': {
                'stock_percent':
                75.58,
                'bond_percent':
                21.55,
                'cash_percent':
                2.35,
                'other_percent':
                0.52,
                'asset_tot':
                4478277223.52,
                'asset_val':
                4428873440.64,
                'source_mark':
                '第二季度报',
                'source':
                '2',
                'enddate':
                '2021-06-30',
                'stock_list': [{
                    'name': '五粮液',
                    'code': '000858',
                    'percent': 4.33,
                    'current_price': 229,
                    'change_percentage': -0.41,
                    'xq_symbol': 'SZ000858',
                    'xq_url': 'https://xueqiu.com/S/SZ000858',
                    'amarket': True
                }, {
                    'name': '药明康德',
                    'code': '603259',
                    'percent': 3.2,
                    'current_price': 128.62,
                    'change_percentage': -1.02,
                    'xq_symbol': 'SH603259',
                    'xq_url': 'https://xueqiu.com/S/SH603259',
                    'amarket': True
                }, {
                    'name': '迈瑞医疗',
                    'code': '300760',
                    'percent': 3.13,
                    'current_price': 347.2,
                    'change_percentage': 0.76,
                    'xq_symbol': 'SZ300760',
                    'xq_url': 'https://xueqiu.com/S/SZ300760',
                    'amarket': True
                }, {
                    'name': '贵州茅台',
                    'code': '600519',
                    'percent': 3.08,
                    'current_price': 1620,
                    'change_percentage': -0.92,
                    'xq_symbol': 'SH600519',
                    'xq_url': 'https://xueqiu.com/S/SH600519',
                    'amarket': True
                }, {
                    'name': '泸州老窖',
                    'code': '000568',
                    'percent': 3.02,
                    'current_price': 179.55,
                    'change_percentage': 0.09,
                    'xq_symbol': 'SZ000568',
                    'xq_url': 'https://xueqiu.com/S/SZ000568',
                    'amarket': True
                }, {
                    'name': '爱尔眼科',
                    'code': '300015',
                    'percent': 2.98,
                    'current_price': 50.7,
                    'change_percentage': -2.5,
                    'xq_symbol': 'SZ300015',
                    'xq_url': 'https://xueqiu.com/S/SZ300015',
                    'amarket': True
                }, {
                    'name': '康龙化成',
                    'code': '300759',
                    'percent': 2.71,
                    'current_price': 184.5,
                    'change_percentage': 2.11,
                    'xq_symbol': 'SZ300759',
                    'xq_url': 'https://xueqiu.com/S/SZ300759',
                    'amarket': True
                }, {
                    'name': '凯莱英',
                    'code': '002821',
                    'percent': 2.67,
                    'current_price': 346,
                    'change_percentage': -1.14,
                    'xq_symbol': 'SZ002821',
                    'xq_url': 'https://xueqiu.com/S/SZ002821',
                    'amarket': True
                }, {
                    'name': '歌尔股份',
                    'code': '002241',
                    'percent': 2.64,
                    'current_price': 39.61,
                    'change_percentage': 0.08,
                    'xq_symbol': 'SZ002241',
                    'xq_url': 'https://xueqiu.com/S/SZ002241',
                    'amarket': True
                }, {
                    'name': '华熙生物',
                    'code': '688363',
                    'percent': 2.51,
                    'current_price': 203,
                    'change_percentage': -1.6,
                    'xq_symbol': 'SH688363',
                    'xq_url': 'https://xueqiu.com/S/SH688363',
                    'amarket': True
                }],
                'bond_list': [{
                    'name': '20国开07',
                    'code': '200207',
                    'percent': 2.72,
                    'xq_symbol': '200207',
                    'xq_url': 'https://xueqiu.com/S/200207',
                    'amarket': False
                }, {
                    'name': '19进出08',
                    'code': '190308',
                    'percent': 2.5,
                    'xq_symbol': '190308',
                    'xq_url': 'https://xueqiu.com/S/190308',
                    'amarket': False
                }, {
                    'name': '15华能集MTN002',
                    'code': '101564021',
                    'percent': 2.28,
                    'xq_symbol': '101564021',
                    'xq_url': 'https://xueqiu.com/S/101564021',
                    'amarket': False
                }, {
                    'name': '20进出12',
                    'code': '200312',
                    'percent': 2.27,
                    'xq_symbol': '200312',
                    'xq_url': 'https://xueqiu.com/S/200312',
                    'amarket': False
                }, {
                    'name': '20进出02',
                    'code': '200302',
                    'percent': 2.25,
                    'xq_symbol': '200302',
                    'xq_url': 'https://xueqiu.com/S/200302',
                    'amarket': False
                }, {
                    'name': '比音转债',
                    'code': '128113',
                    'percent': 0.28,
                    'xq_symbol': '128113',
                    'xq_url': 'https://xueqiu.com/S/128113',
                    'amarket': False
                }, {
                    'name': '柳药转债',
                    'code': '113563',
                    'percent': 0.04,
                    'xq_symbol': '113563',
                    'xq_url': 'https://xueqiu.com/S/113563',
                    'amarket': False
                }, {
                    'name': '鸿路转债',
                    'code': '128134',
                    'percent': 0.02,
                    'xq_symbol': '128134',
                    'xq_url': 'https://xueqiu.com/S/128134',
                    'amarket': False
                }]
            },
            'rate': {
                'fd_code':
                '000001',
                'subscribe_rate':
                '1.0',
                'declare_rate':
                '1.5',
                'withdraw_rate':
                '0.5',
                'discount':
                '0.1',
                'subscribe_discount':
                '0.1',
                'declare_discount':
                '0.1',
                'declare_rate_table': [{
                    'name': '买入金额<100.0万',
                    'value': '1.5'
                }, {
                    'name': '100.0万<=买入金额<500.0万',
                    'value': '1.2'
                }, {
                    'name': '500.0万<=买入金额<1000.0万',
                    'value': '0.8'
                }, {
                    'name': '1000.0万<=买入金额',
                    'value': '1000.0'
                }],
                'withdraw_rate_table': [{
                    'name': '0.0天<持有期限<7.0天',
                    'value': '1.5'
                }, {
                    'name': '7.0天<=持有期限',
                    'value': '0.5'
                }],
                'other_rate_table': [{
                    'name': '基金管理费',
                    'value': '1.5'
                }, {
                    'name': '基金托管费',
                    'value': '0.25'
                }]
            }
        }
        ```
        """
        _url = f'https://danjuanapp.com/djapi/fund/detail/{fund_code}'
        hd = dt_utils.parse_headers(header_str)
        _resp = rget_json(_url, headers=hd)

        if _resp:
            data = _resp.get('data')
            if data:
                position = data.get('fund_position')
                rate = data.get('fund_rates')
                return {'position': position, 'rate': rate}

    @staticmethod
    def remove_duplicate_resort(with_dup_dict_list: list):
        """
        部分数据中含有重复数据需要对其进行去重，同时需要重新排序（按照费率的反序）
        see also:
        [Remove duplicate dict in list in Python - Stack Overflow]
        (https://stackoverflow.com/questions/9427163/remove-duplicate-dict-in-list-in-python)
        Examples:
        ```
        >>> a =  [
        {
            "name": "0.0天<持有期限<7.0天",
            "value": "1.5"
        }, {
            "name": "0.0天<持有期限<30.0天",
            "value": "0.5"
        }, {
            "name": "7.0天<=持有期限<30.0天",
            "value": "0.5"
        }, {
            "name": "30.0天<=持有期限",
            "value": "0.0"
        }, {
            "name": "30.0天<=持有期限",
            "value": "0.0"
        }]
        >>> remove_duplicate_resort(a)
        [{'name': '0.0天<持有期限<7.0天', 'value': '1.5'}, {'name': '7.0天<=持有期限<30.0天', 'value': '0.5'},
               {'name': '30.0天<=持有期限', 'value': '0.0'}]
        ```
        :return:
        """

        with_dup_dict_list_df = pd.DataFrame(with_dup_dict_list)
        # 删除重复数据
        no_duplicated_df = with_dup_dict_list_df.drop_duplicates(subset=['value', 'name'], keep='first')
        # 对于费率相同的数据取后一条
        no_duplicated_value_df = no_duplicated_df.drop_duplicates(subset=['value'], keep='last')
        rmv_list = no_duplicated_value_df.to_dict(orient='records')
        return rmv_list

    def rate(self, fund_code, to_db: bool = False):
        """
        将接口返回数据：
        ```
        {
            'fd_code':'000001',
            'subscribe_rate':'1.0',
            'declare_rate':'1.5',
            'withdraw_rate':'0.5',
            'discount':'0.1',
            'subscribe_discount':'0.1',
            'declare_discount': '0.1',
            'declare_rate_table': [
            {
                'name': '买入金额<100.0万',
                'value': '1.5'
            }, {
                'name': '100.0万<=买入金额<500.0万',
                'value': '1.2'
            }, {
                'name': '500.0万<=买入金额<1000.0万',
                'value': '0.8'
            }, {
                'name': '1000.0万<=买入金额',
                'value': '1000.0'
            }],
            'withdraw_rate_table': [
            {
                'name': '0.0天<持有期限<7.0天',
                'value': '1.5'
            }, {
                'name': '7.0天<=持有期限',
                'value': '0.5'
            }],
            'other_rate_table': [
            {
                'name': '基金管理费',
                'value': '1.5'
            }, {
                'name': '基金托管费',
                'value': '0.25'
            }]
        }
        ```
        :param to_db: 是否保存更新到数据库
        :param fund_code:基金编码
        :return:
        """
        fd_detail = self.fund_detail(fund_code)
        if fd_detail:
            rate = fd_detail.get('rate')
            logger.info(f'rate info:{rate}')
            declare_rate_table = rate.get('declare_rate_table')
            withdraw_rate_table = rate.get('withdraw_rate_table')
            op_info = rate.get('other_rate_table')

            declare_info = list()
            if declare_rate_table:
                declare_info = self.purchase_rate(declare_rate_table, money_key='name', rate_key='value')
                if to_db:
                    self.save_fee_info(fund_code, declare_info, fee_type=2)

            withdraw_info = list()
            if withdraw_rate_table:
                withdraw_info = self.redeem_rate(withdraw_rate_table, time_key='name', rate_key='value')
                if to_db:
                    if fund_code not in ['000074']:
                        self.save_fee_info(fund_code, withdraw_info, fee_type=3)
                    else:
                        logger.warning(f'We think the withdraw_info of {fund_code} is error,just skip it.')

            rate_info = {
                'purchase': declare_info,
                'op': op_info,
                'redeem': withdraw_info,
            }
            return rate_info
        # raise EmptyError(f'The fund_code {fund_code} from remote get empty response,please check the code is
        # validated?')
        return None

    def purchase_parser(self, purchase_info: dict, money_key: str = 'name', rate_key: str = 'value'):
        """
        解析申购信息
        :param rate_key:
        :param money_key:
        :param purchase_info:
        :return:
        """
        range_str = purchase_info.get(money_key)
        rate = purchase_info.get(rate_key)
        if range_str:
            portion_info = self.make_purchase_info(range_str)
            # lower_bounds = portion_info.get('lower')
            upper_bounds = portion_info.get('end_quota')
            if upper_bounds is not None:
                rate_info = {'rate': float(rate) / 10}
            else:
                # 处理最后一个区间使用固定金额的情况
                last_is_rate = float(rate) > 1
                if last_is_rate or float(rate) == 0:
                    rate_info = {'fee_amount': float(rate)}
                else:
                    rate_info = {'rate': float(rate) / 10}

            portion_info.update(rate_info)
            _rule_info = portion_info.copy()
        else:
            # 免费 007471
            start_quota = 0
            amount = 0

            _rule_info = {
                'start_quota': start_quota,
                'end_quota': None,
                'fee_amount': float(amount),
            }
        return _rule_info

    def redeem_parser(self, redeem_info: dict, time_key='time', rate_key='rate') -> Optional[Dict]:
        range_str = redeem_info.get(time_key)
        rate = redeem_info.get(rate_key)
        if range_str:
            _portion_info = self.make_redeem_info(range_str)
            rate_info = {
                'rate': float(rate),
            }
            _portion_info.update(rate_info)
            return _portion_info

    def parse_less_single(self, item_key: str, sorted_li: List):
        """
        蛋卷对于单符号的处理稍微有点复杂
        有可能是：x>7也可能是：7<x
        :param item_key:
        :param sorted_li:
        :return:
        """
        if item_key == 'less_single_o':
            digit_is_first = False
            # 此处有可能条件在区间后面，也有可能条件在区间前面
            bound = sorted_li[1]
            if not bound[0].isdigit():
                digit_is_first = True
                bound = sorted_li[0]
                assert bound[0].isdigit()
        else:
            bound = sorted_li[0]
            digit_is_first = True
            if not bound[0].isdigit():
                digit_is_first = False
                bound = sorted_li[1]
                assert bound[0].isdigit()
        bound_value = self.suffix_str_to_num(bound)
        # 时间序列，默认+1
        if not self.is_money_suffix(bound):
            if item_key == 'less_single_o':
                if digit_is_first:
                    bound_value += 1
                    interval_item = portion.closedopen(bound_value, portion.inf)
                else:
                    interval_item = portion.closedopen(0, bound_value)
            else:
                if digit_is_first:
                    interval_item = portion.closedopen(bound_value, portion.inf)
                else:
                    bound_value += 1
                    interval_item = portion.closedopen(0, bound_value)
        # 金钱的话，直接转为改为闭区间即可
        else:
            if item_key == 'less_single_c':
                interval_item = portion.closedopen(bound_value, portion.inf)
            else:
                if bound_value == 0:
                    bound_value = portion.inf
                interval_item = portion.closedopen(0, bound_value)
        return interval_item


dj_fd = FundFeeRatio()

dj_evl = DanJuanEvl()

if __name__ == '__main__':
    print(dj_evl.valuation())

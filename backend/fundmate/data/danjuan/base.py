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
import copy
import re
from typing import List, Union

import cachetools.func
from xalpha.cons import rget_json

from backend.fundmate import settings, utils
from backend.fundmate.data import utils as dt_utils
from backend.fundmate.excepts import EmptyError, ParseError, UnpackError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import FeeRatio, Fund, InRule, OutRule

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


class DanJuanFundDetail:
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

    def suffix_str_to_num(self, suffix_str: str, replace_flag: str = 'w') -> Union[int, float]:
        """
        带后缀的字符串进行截取，最终获取到数字
        100万 -> 1000000
        7.0天 -> 7
        2.0年 -> 720
        :param replace_flag: 替代标识，可以替代的后缀
        :param suffix_str: 被替换字符
        :return:
        """
        replace_map = {
            'w': '万',
            'd': '天',
            'n': '年',
        }
        if replace_map.get('n') in suffix_str:
            replace_flag = 'n'
        replace_str = replace_map.get(replace_flag)
        # FIXME：see also: https://docs.python.org/3/library/stdtypes.html#str.removesuffix
        if suffix_str.endswith(replace_str):
            '''
            ```
            >>> 'MiscTests'.removesuffix('Tests')
            'Misc'
            >>> 'TmpDirMixin'.removesuffix('Tests')
            'TmpDirMixin'
            ```
            '''
            no_suffix_str = suffix_str.replace(replace_str, '')
            if replace_flag == 'w':
                return float(no_suffix_str) * 10000
            elif replace_flag == 'd':
                int_day = 7
                try:
                    int_day = int(float(no_suffix_str))
                except ValueError:
                    if no_suffix_str.startswith('='):
                        # fixme:000005,需要特殊处理（(0,6]）
                        no_suffix_str = no_suffix_str.replace('=', '')
                        int_day = int(float(no_suffix_str)) + 1
            else:
                # convert year to day
                int_day = int(float(no_suffix_str)) * 365
            return int_day

        raise ValueError(f'The suffix_str:{suffix_str} is not end with {replace_str}.')

    def parse_first(self, range_str: str) -> float:
        """
        买入金额<100.0万  -> 1000000
        :param range_str:
        :return:
        """
        split_signal = '<'
        if split_signal in range_str:
            data_li = range_str.split(split_signal)
            data_str = data_li[-1]
            float_wan = self.suffix_str_to_num(data_str)
            return float_wan
        raise ValueError(f"Don't have {split_signal} in the range_str:{range_str}.")

    def first_quota(self, first_info: dict) -> dict:
        """
        有始有终
        :param first_info:
        :param rate:
        :return:
        """
        range_str = first_info.get('name')
        rate = first_info.get('value')
        end_quota = self.parse_first(range_str)
        _rule_info = {
            'start_quota': 0,
            'end_quota': end_quota,
            'rate': float(rate),
        }
        return _rule_info

    def _parse_both_limit(self, qt_name: str, p_type: str = 'q') -> List[float]:
        """
        对于一个区间字符串（详见示例），使用正则提取前后区间的数字并返回

        Examples:
        ```
        >>> '100.0万<=买入金额<500.0万'
        >>> [1000000.0,5000000.0]
        >>> "0.0天<持有期限<30.0天"
        >>> [0,30]
        >>> "365.0天<=持有期限<2.0年"
        >>> [365,730]
        >>> "2.0年<=持有期限<3.0年"
        >>> [730,1095]
        ```
        :param qt_name: 被匹配的字符串，从中匹配数字
        :param p_type: 匹配规则，可以是额度（q）或者天数（d）
        :return:
        """
        except_types = ['q', 'd']
        if p_type not in except_types:
            raise KeyError(f'The p_type: {p_type} should in {except_types},while `q` for quota,`d` for day.')

        if qt_name.endswith('年'):
            if p_type == 'd':
                day_year_match_exp = r'(\d+.\d+)天.+(\d+.\d+)年'
                regex = re.compile(day_year_match_exp)
                dy_reg_mat = regex.findall(qt_name)
                if dy_reg_mat:
                    start_day, end_year = dy_reg_mat[0]
                    no_suffix_li = [int(float(start_day)), int(float(end_year)) * 365]
                    return no_suffix_li
                else:
                    # 2.0年<=持有期限<3.0年
                    yy_match_exp = r'(\d+.\d+)年.+(\d+.\d+)年'
                    regex = re.compile(yy_match_exp)
                    dy_reg_mat = regex.findall(qt_name)
                    if dy_reg_mat:
                        ret = dy_reg_mat[0]
                        no_suffix_li = [int(float(year)) * 365 for year in ret]
                        return no_suffix_li

        if p_type == 'q':
            match_exp = r'(\d+.\d+)万'
        else:
            match_exp = r'(\d+.\d+)天'

        regex = re.compile(match_exp)
        reg_mat = regex.findall(qt_name)
        if reg_mat:
            if p_type == 'q':
                # 匹配出来是万，需要转换为元
                no_suffix_li = [float(num) * 10000 for num in reg_mat]
            else:
                no_suffix_li = [int(float(num)) for num in reg_mat]
            return no_suffix_li
        # TODO：split_signal不再需要
        raise ValueError(f"The given str: {qt_name} doesn't match regexp.")

    def parse_middle(self, mid_list):
        """
        [{
                'name': '100.0万<=买入金额<500.0万',
                'value': '1.2'
            }, {
                'name': '500.0万<=买入金额<1000.0万',
                'value': '0.8'
            }]
        :return:
        """
        mid_qta = []
        for item in mid_list:
            name = item.get('name')
            rate = item.get('value')
            float_wan_li = self._parse_both_limit(name)
            s_qt, e_qt = float_wan_li
            qt_info = {
                'start_quota': s_qt,
                'end_quota': e_qt,
                'rate': float(rate),
            }
            mid_qta.append(qt_info)
        return mid_qta

    def parse_last(self, range_str: str, replace_flag='w', split_signal: str = '<=') -> Union[float, int]:
        """
        Examples:
        ```
        >>> '1000.0万<=买入金额'
        >>>10000000.0
        >>> '180.0天<=持有期限'
        >>> 180
        ```
        :param range_str:
        :param replace_flag:
        :param split_signal:
        :return:
        """
        if split_signal in range_str:
            data_li = range_str.split(split_signal)
            data_str = data_li[0]
            no_suffix_num = self.suffix_str_to_num(data_str, replace_flag=replace_flag)
            return no_suffix_num
        else:
            if '<' in range_str:
                # 270.0天<持有期限
                no_suffix_num = self.parse_last(range_str, replace_flag=replace_flag, split_signal='<')
                return no_suffix_num

            raise ValueError(f"Don't have {split_signal} in the range_str:{range_str}.")

    def last_quota(self, last_info: dict) -> dict:
        """
        结束时只有开始值，此时按照固定额收费
        """
        range_str = last_info.get('name')
        amount = last_info.get('value')
        start_quota = self.parse_last(range_str)

        _rule_info = {
            'start_quota': start_quota,
            'end_quota': None,
            'fee_amount': float(amount),
        }
        return _rule_info

    def last_day(self, last_info: dict):
        """
        最低档赎回费信息
        :param last_info:
        :return:
        """
        range_str = last_info.get('name')
        start_day = self.parse_last(range_str, replace_flag='d')
        rate = last_info.get('value')
        _rule_info = {
            'start_day': start_day,
            'end_day': 0,
            'rate': float(rate),
        }
        return _rule_info

    def declare_rate(self, declare_rate_table: list) -> Union[list, None]:
        if len(declare_rate_table) >= 2:
            first, *mid, last = declare_rate_table
            f_qt = self.first_quota(first)
            mid_qt = list()
            l_qt = list()
            if mid:
                mid_qt = self.parse_middle(mid)
            if last:
                l_qt = self.last_quota(last)
            qt_list = [f_qt]
            if mid_qt:
                qt_list.extend(mid_qt)
            if l_qt:
                qt_list.append(l_qt)
        elif len(declare_rate_table) == 1:
            # {'name': '0.0万<买入金额', 'value': '0.0'}
            # 费率与购入金额无关（固定费率）
            last = declare_rate_table[0]
            l_qt = self.last_quota(last)
            qt_list = [l_qt]
        else:
            raise UnpackError(f'declare_rate_table:{declare_rate_table}')
        return qt_list

    @staticmethod
    def remove_duplicate_resort(dup_dict):
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
        >>> self.remove_duplicate_resort(a)
        >>> [{'name': '0.0天<持有期限<7.0天', 'value': '1.5'},
             {'name': '0.0天<持有期限<30.0天', 'value': '0.5'},
             {'name': '7.0天<=持有期限<30.0天', 'value': '0.5'},
             {'name': '30.0天<=持有期限', 'value': '0.0'}]
        ```
        :return:
        """
        rmv_list = [dict(t) for t in {tuple(d.items()) for d in dup_dict}]
        rmv_list.sort(key=lambda x: x['value'], reverse=True)
        return rmv_list

    def _parse_day_have_both(self, mid_info: Union[list, dict]) -> list:
        """"
        两边数值，中间分隔符的情况
        Examples:

        ## 第一种情况
        >>> [{
            "name": "7.0天<=持有期限<30.0天",
            "value": "0.5"
        }, {
            "name": "30.0天<=持有期限<180.0天",
            "value": "0.1"
        }]

        ## 第二种情况

        >>> [{
            "name": "0.0天<持有期限<7.0天",
            "value": "1.5"
        }]

        """

        def parse_item(mid_info_: dict) -> dict:
            """
            解析收费规则
            :param mid_info_:
            :return:
            """
            range_str = mid_info_.get('name')
            rate = mid_info_.get('value')
            float_day_li = self._parse_both_limit(range_str, p_type='d')
            try:
                s_qt, e_qt = float_day_li
            except ValueError as e:
                err_msg = f'Error{e} to unpack {float_day_li},raw str is {range_str}'
                # 不够两个无法处理
                logger.error(err_msg)
                raise ParseError(err_msg)
            '''
            hack：特殊数据处理
            convert:
            {'start_day': 6, 'end_day': 91, 'rate': 0.3},
              {'start_day': 90, 'end_day': 181, 'rate': 0.2},
              {'start_day': 180, 'end_day': 271, 'rate': 0.1},
            to:
              {'start_day': 7, 'end_day': 90, 'rate': 0.3},
              {'start_day': 90, 'end_day': 180, 'rate': 0.2},
              {'start_day': 180, 'end_day': 270, 'rate': 0.1},
            '''
            if e_qt:
                if str(e_qt).endswith('1'):
                    e_qt -= 1
                    if s_qt == 6:
                        s_qt = 7
                _results = {
                    'start_day': s_qt,
                    'end_day': e_qt,
                    'rate': float(rate),
                }
                return _results

        results = []
        if isinstance(mid_info, list):
            for item in mid_info:
                qt_info = parse_item(item)
                results.append(qt_info)
        else:
            results = parse_item(mid_info)
        return results

    def withdraw_rate(self, raw_withdraw_rate_table: list):
        """
        将数据：
        ```
        # 注意此数据中 raw data 本身有重复数据（001778）
        [{
            "name": "0.0天<持有期限<7.0天",
            "value": "1.5"
        }, {
            "name": "7.0天<=持有期限<30.0天",
            "value": "0.5"
        }, {
            "name": "30.0天<=持有期限<180.0天",
            "value": "0.1"
        }, {
            "name": "180.0天<=持有期限",
            "value": "0.0"
        }]
        ```
        :return:
        """
        withdraw_rate_table = self.remove_duplicate_resort(raw_withdraw_rate_table)
        if len(withdraw_rate_table) >= 2:
            *no_last, last = withdraw_rate_table
            try:
                qt_list = self._parse_day_have_both(no_last)  # 解析区间值
            except ParseError:
                qt_list = list()
            if last:
                l_qt = self.last_day(last)
                qt_list.append(l_qt)
        else:
            raise UnpackError(f'withdraw_rate_table:{withdraw_rate_table}')
        return qt_list

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
            declare_rate_table = rate.get('declare_rate_table')
            withdraw_rate_table = rate.get('withdraw_rate_table')

            declare_info = list()
            if declare_rate_table:
                declare_info = self.declare_rate(declare_rate_table)
                if to_db:
                    self.save_fee_info(fund_code, declare_info, fee_type=2)

            withdraw_info = list()
            if withdraw_rate_table:
                withdraw_info = self.withdraw_rate(withdraw_rate_table)
                if to_db:
                    if fund_code not in ['000074']:
                        self.save_fee_info(fund_code, withdraw_info, fee_type=3)
                    else:
                        logger.warning(f'We think the withdraw_info of {fund_code} is error,just skip it.')

            rate_info = {
                'declare_info': declare_info,
                'withdraw_info': withdraw_info,
            }
            return rate_info
        raise EmptyError(f'The fund_code {fund_code} from remote get empty response,please check the code is validate?')

    @staticmethod
    def save_fee_info(fund_code: str, fee_info_tb: list, fee_type: int):
        """
        申购、赎回费率写入数据库
        FIXME: duplicated with transfer_rule
        :param fund_code: 基金编码
        :param fee_info_tb: 费率信息表
        :param fee_type: 费率类型
        :return:
        """
        key = 'out_rule_id'  # 字典的key
        if fee_type == 2:
            key = 'in_rule_id'
            class_name = InRule
        else:
            class_name = OutRule

        fee_types = settings.FEE_TYPE.values()
        if fee_type not in fee_types:
            raise KeyError(f'The fee type should in {fee_types}')

        _fund_inst = Fund.filter_by_code(fund_code)
        fund_id = _fund_inst.id

        for rule_info in fee_info_tb:
            # 要么按照费率收费要么按照金额收费，至少有一个
            cp_rf = copy.deepcopy(rule_info)
            if 'rate' in cp_rf:
                fare_ratio = cp_rf.pop('rate')
                rate = float(fare_ratio) if not isinstance(fare_ratio, float) else fare_ratio
                fee_amount = None
            else:
                rate = None
                fee_amount = cp_rf.pop('fee_amount')
            rule_inst = class_name.insert_or_update(cp_rf, do_log_flag=True, **cp_rf)
            rule_id = rule_inst.id

            _rate_info = {
                key: rule_id,
                'fund_id': fund_id,  # **注意**：在创建时，必须有fund_id
                'fee_type': fee_type,
                'rate': rate,
                'fee_amount': fee_amount,
            }
            query_args = {'fund_id': fund_id, key: rule_id, 'fee_type': fee_type}
            FeeRatio.insert_or_update(query_args, do_log_flag=True, **_rate_info)


dj_fd = DanJuanFundDetail()

dj_evl = DanJuanEvl()

if __name__ == '__main__':
    print(dj_evl.valuation())

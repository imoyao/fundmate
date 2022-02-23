#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/30 17:43
import random
import time
from typing import Optional, Union

from xalpha.cons import JSONDecodeError, rpost_json

from backend.fundmate.data import utils as dt_utils
from backend.fundmate.excepts import CrawlerException, ParseError, UnpackError
from backend.fundmate.exts.flask_loguru import logger

_HEADER_STR = '''authority: api.jiucaishuo.com
method: POST
path: /v2/kjtl/getbasedata
scheme: https
accept: application/json, text/plain, */*
accept-encoding: gzip, deflate, br
accept-language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7
content-length: 661
content-type: application/json;charset=UTF-8
dnt: 1
origin: https://funddb.cn
sec-ch-ua: "Chromium";v="92", " Not A;Brand";v="99", "Microsoft Edge";v="92"
sec-ch-ua-mobile: ?0
sec-fetch-dest: empty
sec-fetch-mode: cors
sec-fetch-site: cross-site
user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107''' \
              '''Safari/537.36 Edg/92.0.902.55'''


class FundDB:

    def kjtl(self, is_full: bool = True) -> dict:
        """
        恐惧贪婪指数
        """
        fear_href = 'https://funddb.cn/tool/fear'
        url = 'https://api.jiucaishuo.com/v2/kjtl/getbasedata'
        data = '''{"type":"pc","data_source":"xichou","version":"1.6.0",
        "authtoken":"ddQYkiZQ087Z5Kr+ER5CmQMFCpjuC/qW","act_time":1627638543548,"tirgkjfs":"08","abiokytke":"0b",
        "u54rg5d":"b3","kf54ge7":"e","tiklsktr4":"8","lksytkjh":"c14c","sbnoywr":"53","bgd7h8tyu54":"54",
        "y654b5fs3tr":"5","bioduytlw":"a","bd4uy742":"f","h67456y":"1c1","bvytikwqjk":"54","ngd4uy551":"c1",
        "bgiuytkw":"9f","nd354uy4752":"d","ghtoiutkmlg":"513","bd24y6421f":"31","tbvdiuytk":"1","ibvytiqjek":"45",
        "jnhf8u5231":"9f","fjlkatj":"b35","hy5641d321t":"1f","iogojti":"1","ngd4yut78":"13","nkjhrew":"f",
        "yt447e13f":"4","n3bf4uj7y7":"1","nbf4uj7y432":"0b","yi854tew":"2d","h13ey474":"2de","quikgdky":"7d"} '''
        hd = dt_utils.parse_headers(_HEADER_STR)
        try:
            resp = rpost_json(url, headers=hd, data=data)
        except JSONDecodeError:
            raise CrawlerException('对方反爬机制导致错误，请稍候重试……')

        info = None
        if resp and resp.get('code') == 0:
            data = resp.get('data')

            current_date = data.get('current_time')
            temper = data.get('num')
            desc = data.get('status_str')
            ov = {
                'update_date': current_date,
                'temper': temper,
                'desc': desc,
                'href': fear_href,
            }

            info = {
                'overview': ov,
            }
            if is_full:
                # 解析信息并重新组装
                detail_list = data.get('list')
                ovl_info = list()
                for item in detail_list:
                    dg = item.get('data').get('series')[0].get('data')
                    desc = item.get('status_str')
                    item_info = {
                        'temper': f'{dg * 100:.2f}',  # 两位小数
                        'desc': desc
                    }
                    ovl_info.append(item_info)

                info_key = ['yesterday', 'last_week', 'last_month', 'last_year']
                amend_info = dict(zip(info_key, ovl_info))

                info.update({'details': amend_info})

        return info


class FundFeeRatio(dt_utils.BaseRatio):

    def rate(self, fund_code: str, to_db: bool = False) -> Optional[dict]:
        """
        origin: https://funddb.cn/site/fund_details?fund_code=001714
        基金概览-费率信息
        :return:
        """
        _url = 'https://api.jiucaishuo.com/v2/fund-lists/fundrate'
        t = time.time()
        data = {
            "code": fund_code,
            "type": "pc",
            "data_source": "xichou",
            "version": "1.6.0",
            "authtoken": "ddQYkiZQ087Z5Kr+ER5CmQMFCpjuC/qW",
            "act_time": int(round(t * 1000)),
            "tirgkjfs": "32",
            "abiokytke": "86",
            "u54rg5d": "5c",
            "kf54ge7": "4",
            "tiklsktr4": "2",
            "lksytkjh": "8425",
            "sbnoywr": "48",
            "bgd7h8tyu54": "5f",
            "y654b5fs3tr": "0",
            "bioduytlw": "8",
            "bd4uy742": "4",
            "h67456y": "384",
            "bvytikwqjk": "5f",
            "ngd4uy551": "84",
            "bgiuytkw": "69",
            "nd354uy4752": "1",
            "ghtoiutkmlg": "0c6",
            "bd24y6421f": "8d",
            "tbvdiuytk": "3",
            "ibvytiqjek": "da",
            "jnhf8u5231": "69",
            "fjlkatj": "5cd",
            "hy5641d321t": "d4",
            "iogojti": "d",
            "ngd4yut78": "c6",
            "nkjhrew": "4",
            "yt447e13f": "e",
            "n3bf4uj7y7": "4",
            "nbf4uj7y432": "86",
            "yi854tew": "51",
            "h13ey474": "514",
            "quikgdky": "fe"
        }
        hd = dt_utils.parse_headers(_HEADER_STR)
        # [httprequest - Python Request Post with param data - Stack Overflow]
        # (https://stackoverflow.com/questions/15900338/python-request-post-with-param-data)
        try:
            resp = rpost_json(_url, headers=hd, json=data)
        except JSONDecodeError:
            # 爬太快，数据处理不过来？
            # [python - How to get a random number between a float range? - Stack Overflow]
            # (https://stackoverflow.com/questions/6088077/how-to-get-a-random-number-between-a-float-range)
            timeout = round(random.uniform(0.3, 0.7), 2)
            time.sleep(timeout)
            try:
                resp = rpost_json(_url, headers=hd, json=data)
            except JSONDecodeError:
                resp = None
                try:
                    msg = f'Fund code:{fund_code}, {resp.text}'
                    logger.error(msg)
                    raise CrawlerException(msg)
                except AttributeError:
                    raise CrawlerException('反爬机制导致错误，请稍候重试……')

        code = resp.get('code')
        if code == 0:
            data = resp.get('data')
            purchase = data.get('sg')
            op = data.get('gl')
            redeem = data.get('sh')
            '''
            {'buy': [{'money': '购买金额 < 100万',
               'time': '',
               'source': '1.50%',
               'rate': '0.15%'},
              {'money': '100万 ≤ 购买金额 < 500万',
               'time': '',
               'source': '1.20%',
               'rate': '0.12%'},
              {'money': '500万 ≤ 购买金额 < 1000万',
               'time': '',
               'source': '0.80%',
               'rate': '0.08%'},
              {'money': '购买金额 ≥ 1000万',
               'time': '',
               'source': '1000元/笔',
               'rate': '1000元/笔'}],
             'op': [{'name': '管理费率', 'val': '1.50% (每年)'},
              {'name': '托管费率', 'val': '0.25% (每年)'},
              {'name': '销售服务费率', 'val': '0.00% (每年)'}],
             'redeem': [{'money': '', 'time': '持有期限 < 7天', 'source': '', 'rate': '1.50%'},
              {'money': '', 'time': '持有期限 ≥ 7天', 'source': '', 'rate': '0.50%'}]}
    
            '''
            purchase_info = None
            redeem_info = None
            if purchase:
                try:
                    purchase_info = self.declare_rate(purchase)
                except ValueError:
                    raise CrawlerException(f'基金 {fund_code} 处理申购信息 {purchase} 出错！')
            if redeem:
                try:
                    redeem_info = self.parse_redeem_info(redeem)
                except ValueError:
                    raise CrawlerException(f'基金 {fund_code} 处理赎回信息 {redeem} 出错！')

            if to_db:
                if purchase_info:
                    self.save_fee_info(fund_code, purchase_info, fee_type=2)
                if redeem_info:
                    try:
                        self.save_fee_info(fund_code, redeem_info, fee_type=3)
                    except TypeError as e:
                        raise CrawlerException(f'基金 {fund_code} 保存赎回信息 {redeem_info} 出错，出错信息：{e}！')

            info = {
                'purchase': purchase_info,
                'op': op,
                'redeem': redeem_info,
            }
            return info

    def parse_redeem_info(self, redeem_list: list):
        ret = self.withdraw_rate(redeem_list)
        return ret

    def withdraw_rate(self, withdraw_rate_table: list):
        """
        赎回费率信息处理
        :return:
        """
        if len(withdraw_rate_table) == 1:  # 只有一个，即免费
            free_item = withdraw_rate_table[0]
            l_qt = self.last_day(free_item)
            qt_list = [l_qt]
        # 韭圈第一个是开区间的
        elif len(withdraw_rate_table) == 2:
            first, last = withdraw_rate_table
            try:
                first_day_fee_info = self.parse_first_day_range(first)  # 解析阈值
                qt_list = [first_day_fee_info]
            except ParseError:
                qt_list = list()
            if last:
                l_qt = self.last_day(last)
                qt_list.append(l_qt)
        elif len(withdraw_rate_table) > 2:
            first, *mid_items, last = withdraw_rate_table
            try:
                first_day_fee_info = self.parse_first_day_range(first)  # 解析阈值
                first_list = [first_day_fee_info]
            except ParseError:
                first_list = None
            try:
                _mid_list = self._parse_day_have_both(mid_items)  # 解析中间阈值
                if first_list:
                    qt_list = first_list + _mid_list
                elif _mid_list:
                    qt_list = _mid_list
                else:
                    qt_list = list()
            except ParseError:
                qt_list = list()

            if last:
                l_qt = self.last_day(last)
                qt_list.append(l_qt)
        else:
            raise UnpackError(f'withdraw_rate_table:{withdraw_rate_table}')
        return qt_list

    def parse_first_day_range(self, range_item: dict) -> dict:
        range_str = range_item.get('time')
        rate = range_item.get('rate')
        float_day_li = self.first_day(range_str)
        s_qt, e_qt = float_day_li
        _results = {
            'start_day': s_qt,
            'end_day': e_qt,
            'rate': self.remove_percent(rate),
        }
        return _results

    def remove_percent(self, x: str) -> float:
        """
        去除字符串的%字符

        >>> remove_percent('1.5%')
        1.5

        :param x:
        :return:
        """
        return float(x.strip('%'))

    def first_quota(self, first_info: dict) -> dict:
        """
        将第一行的额度转化为前后均有限制的额度
        :param first_info:
        :return:
        """
        range_str = first_info.get('money')
        rate = first_info.get('rate')
        end_quota = self.parse_first(range_str)
        _rule_info = {
            'start_quota': 0,
            'end_quota': end_quota,
            'rate': self.remove_percent(rate),
        }
        return _rule_info

    def parse_middle(self, mid_list):
        """
        [{
                'money': '100.0万<=买入金额<500.0万',
                'rate': '1.2'
            }, {
                'money': '500.0万<=买入金额<1000.0万',
                'rate': '0.8'
            }]
        :return:
        """
        mid_qta = []
        for item in mid_list:
            name = item.get('money')
            rate = item.get('rate')
            float_wan_li = self._parse_both_limit(name)
            s_qt, e_qt = float_wan_li
            qt_info = {
                'start_quota': s_qt,
                'end_quota': e_qt,
                'rate': self.remove_percent(rate),
            }
            mid_qta.append(qt_info)
        return mid_qta

    def last_quota(self, last_info: dict) -> dict:
        """
        结束时只有开始值，此时按照固定额收费
        """
        range_str = last_info.get('money')
        amount_str = last_info.get('rate')
        if range_str:
            start_quota = self.parse_last(range_str, split_signal='≥')  # 切割符处理
            amount = amount_str.replace('元/笔', '')
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

    def _parse_day_have_both(self, mid_info: Union[list, dict]) -> list:
        """"
        两边数值，中间分隔符的情况
        """

        def parse_item(mid_info_: dict) -> dict:
            """
            解析收费规则
            :param mid_info_:
            :return:
            """
            range_str = mid_info_.get('time')
            rate = mid_info_.get('rate')
            try:
                float_day_li = self._parse_both_limit(range_str, p_type='d')
            except ValueError as e:
                err_msg = f'Error: {e} to parse raw str: {range_str}'
                logger.error(err_msg)
                float_day_li = self.first_day(range_str)
            try:
                s_qt, e_qt = float_day_li
            except ValueError as e:
                err_msg = f'Error: {e} to unpack {float_day_li},raw str is {range_str}'
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
                    'rate': self.remove_percent(rate),
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

    def last_day(self, last_info: dict, split_signal: str = '≥'):
        """
        最低档赎回费信息
        :param split_signal:
        :param last_info:
        :return:
        """
        range_str = last_info.get('time')
        rate = last_info.get('rate')
        start_day = self.parse_last(range_str, replace_flag='d', split_signal=split_signal)
        _rule_info = {
            'start_day': start_day,
            'end_day': None,
            'rate': self.remove_percent(rate),
        }
        return _rule_info

    def first_day(self, range_str: str):
        """
        最低档赎回费信息
        >>> first_day('持有期限 < 7天')
        [0,7]
        :param range_str:
        :return:
        """
        end_day = self.parse_last(range_str, replace_flag='d', split_signal='<')
        zero_start_rule_li = [0, end_day]
        return zero_start_rule_li


jq_app = FundDB()
jq_fr = FundFeeRatio()
if __name__ == '__main__':
    print(jq_app.kjtl(is_full=True))
    ratio = jq_fr.rate('001718')
    print(ratio)

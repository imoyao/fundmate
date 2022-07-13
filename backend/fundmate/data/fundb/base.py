#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/30 17:43
import random
import time
from typing import Optional

from requests.exceptions import JSONDecodeError as RJSONDecodeError
from retry import retry
from xalpha.cons import JSONDecodeError as XJSONDecodeError
from xalpha.cons import rpost_json

from backend.fundmate import settings
from backend.fundmate.data.utils import base as dt_utils
from backend.fundmate.data.utils import ratio
from backend.fundmate.excepts import CrawlerException, IsClosedDurationError, ParseError
from backend.fundmate.exts.flask_loguru import logger

# noqa: Q001
_HEADER_STR = """authority: api.jiucaishuo.com
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
user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107""" \
              """Safari/537.36 Edg/92.0.902.55"""


def delay_timeout() -> float:
    """
    随机延时，参阅：
    [python - How to get a random number between a float range? - Stack Overflow]
    (https://stackoverflow.com/questions/6088077/how-to-get-a-random-number-between-a-float-range)

    :return:
    """
    timeout = round(random.uniform(0.3, 0.7), 2)
    return timeout


class FundDB:

    @retry(exceptions=(XJSONDecodeError, RJSONDecodeError, CrawlerException),
           tries=10,
           delay=delay_timeout(),
           backoff=2,
           max_delay=20)
    def kjtl(self, is_full: bool = True) -> dict:
        """
        恐惧贪婪指数
        """
        fear_href = 'https://funddb.cn/tool/fear'
        url = 'https://api.jiucaishuo.com/v2/kjtl/getbasedata'
        data = """{"type":"pc","data_source":"xichou","version":"1.6.0",
        "authtoken":"ddQYkiZQ087Z5Kr+ER5CmQMFCpjuC/qW","act_time":1627638543548,"tirgkjfs":"08","abiokytke":"0b",
        "u54rg5d":"b3","kf54ge7":"e","tiklsktr4":"8","lksytkjh":"c14c","sbnoywr":"53","bgd7h8tyu54":"54",
        "y654b5fs3tr":"5","bioduytlw":"a","bd4uy742":"f","h67456y":"1c1","bvytikwqjk":"54","ngd4uy551":"c1",
        "bgiuytkw":"9f","nd354uy4752":"d","ghtoiutkmlg":"513","bd24y6421f":"31","tbvdiuytk":"1","ibvytiqjek":"45",
        "jnhf8u5231":"9f","fjlkatj":"b35","hy5641d321t":"1f","iogojti":"1","ngd4yut78":"13","nkjhrew":"f",
        "yt447e13f":"4","n3bf4uj7y7":"1","nbf4uj7y432":"0b","yi854tew":"2d","h13ey474":"2de","quikgdky":"7d"}"""
        hd = dt_utils.parse_headers(_HEADER_STR)
        try:
            resp = rpost_json(url, headers=hd, data=data)
        except (XJSONDecodeError, RJSONDecodeError):
            raise CrawlerException('对方反爬机制导致错误，请稍候重试……') from (XJSONDecodeError, RJSONDecodeError)

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


class FundFeeRatio(ratio.BaseRatio):

    @retry(exceptions=(XJSONDecodeError, RJSONDecodeError, CrawlerException),
           tries=5,
           delay=delay_timeout(),
           backoff=2,
           max_delay=5)
    def rate(self, fund_code: str, to_db: bool = False) -> Optional[dict]:
        """
        origin: https://funddb.cn/site/fund_details?fund_code=001714
        基金概览-费率信息
        :return:
        """
        _url = 'https://api.jiucaishuo.com/v2/fund-lists/fundrate'
        t = time.time()
        data = {
            'code': fund_code,
            'type': 'pc',
            'data_source': 'xichou',
            'version': '1.6.0',
            'authtoken': 'ddQYkiZQ087Z5Kr+ER5CmQMFCpjuC/qW',
            'act_time': int(round(t * 1000)),
            'tirgkjfs': '32',
            'abiokytke': '86',
            'u54rg5d': '5c',
            'kf54ge7': '4',
            'tiklsktr4': '2',
            'lksytkjh': '8425',
            'sbnoywr': '48',
            'bgd7h8tyu54': '5f',
            'y654b5fs3tr': '0',
            'bioduytlw': '8',
            'bd4uy742': '4',
            'h67456y': '384',
            'bvytikwqjk': '5f',
            'ngd4uy551': '84',
            'bgiuytkw': '69',
            'nd354uy4752': '1',
            'ghtoiutkmlg': '0c6',
            'bd24y6421f': '8d',
            'tbvdiuytk': '3',
            'ibvytiqjek': 'da',
            'jnhf8u5231': '69',
            'fjlkatj': '5cd',
            'hy5641d321t': 'd4',
            'iogojti': 'd',
            'ngd4yut78': 'c6',
            'nkjhrew': '4',
            'yt447e13f': 'e',
            'n3bf4uj7y7': '4',
            'nbf4uj7y432': '86',
            'yi854tew': '51',
            'h13ey474': '514',
            'quikgdky': 'fe'
        }
        hd = dt_utils.parse_headers(_HEADER_STR)
        # [httprequest - Python Request Post with param data - Stack Overflow]
        # (https://stackoverflow.com/questions/15900338/python-request-post-with-param-data)
        try:
            resp = rpost_json(_url, headers=hd, json=data)
        except (XJSONDecodeError, RJSONDecodeError):
            msg = f'基金编码：{fund_code}反爬机制导致错误，请稍候重试……'
            logger.error(msg)
            raise CrawlerException(msg) from (XJSONDecodeError, RJSONDecodeError)

        code = resp.get('code')
        if code == 0:
            data = resp.get('data')
            purchase = data.get('sg')
            op = data.get('gl')
            redeem = data.get('sh')
            """
            示例数据
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
            """
            logger.info(f'Fund: {fund_code}, purchase: {purchase}, redeem: {redeem}')

            purchase_info = None
            redeem_info = None
            if purchase:
                try:
                    purchase_info = self.purchase_rate(purchase, money_key='money', rate_key='rate')
                except ValueError:
                    raise CrawlerException(f'基金 {fund_code} 处理申购信息 {purchase} 出错！') from ValueError
            if redeem:
                try:
                    redeem_info = self.redeem_rate(redeem)
                except (ValueError, ParseError, IsClosedDurationError):
                    raise CrawlerException(f'基金 {fund_code} 处理赎回信息 {redeem} 出错！') from (ValueError, ParseError,
                                                                                        IsClosedDurationError)

            if to_db:
                if purchase_info:
                    self.save_fee_info(fund_code, purchase_info, fee_type=settings.FeeTypeEnum.purchase)
                if redeem_info:
                    try:
                        self.save_fee_info(fund_code, redeem_info, fee_type=settings.FeeTypeEnum.redeem)
                    except (TypeError, ParseError) as e:
                        raise CrawlerException(f'基金 {fund_code} 保存赎回信息 {redeem_info} 出错，出错信息：{e}！') from (TypeError,
                                                                                                          ParseError)

            info = {
                'purchase': purchase_info,
                'op': op,
                'redeem': redeem_info,
            }
            return info


jq_app = FundDB()
jq_fr = FundFeeRatio()
if __name__ == '__main__':
    print(jq_app.kjtl(is_full=True))
    ratio = jq_fr.rate('001718')
    print(ratio)

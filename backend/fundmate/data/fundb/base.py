#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/30 17:43
import enum
import time
from typing import Dict, Optional

from requests.exceptions import JSONDecodeError as RJSONDecodeError
from retry import retry
from xalpha.cons import JSONDecodeError as XJSONDecodeError
from xalpha.cons import rget_json, rpost_json

from backend.fundmate import settings
from backend.fundmate.data.utils import ratio
from backend.fundmate.excepts import CrawlerException, IsClosedDurationError, ParseError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.libs.dk_enums import BaseTypeEnum, ChoiceTypeIntegerDk


JG = ChoiceTypeIntegerDk(2, 'PH', '军工')
QS = ChoiceTypeIntegerDk(3, 'PH', '券商')
XNC = ChoiceTypeIntegerDk(4, 'TF', '新能车')
XP = ChoiceTypeIntegerDk(5, 'TF', '芯片')
HT = ChoiceTypeIntegerDk(6, 'PH', '恒生TECH')
GF = ChoiceTypeIntegerDk(7, 'TF', '光伏')
DC = ChoiceTypeIntegerDk(8, 'TF', '电池')


@enum.unique
class IndustryEnum(BaseTypeEnum):
    """
    追涨杀跌（择时）
    """
    JG = JG
    QS = QS
    XNC = XNC
    XP = XP
    HT = HT
    GF = GF
    DC = DC


class FundDB:

    @retry(exceptions=(XJSONDecodeError, RJSONDecodeError, CrawlerException),
           tries=10,
           delay=0.5,
           backoff=2,
           jitter=(0.3, 0.7),
           max_delay=20)
    def kjtl(self, is_full: bool = True) -> dict:
        """
        恐惧贪婪指数
        """
        fear_href = 'https://funddb.cn/tool/fear'
        url = 'https://api.jiucaishuo.com/v2/kjtl/getbasedata'
        try:
            resp = rget_json(url)
        except (XJSONDecodeError, RJSONDecodeError) as e:
            raise CrawlerException(f'对方反爬机制导致错误{e}，请稍候重试……') from e

        info = None
        if resp and resp.get('code') == 0:
            data = resp.get('data')

            current_date = data.get('current_time')
            temperature = data.get('num')
            desc = data.get('status_str')
            ov = {
                'update_date': current_date,
                'temperature': temperature,
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
                        'temperature': f'{dg * 100:.2f}',  # 两位小数
                        'desc': desc
                    }
                    ovl_info.append(item_info)

                info_key = ['yesterday', 'last_week', 'last_month', 'last_year']
                amend_info = dict(zip(info_key, ovl_info))

                info.update({'details': amend_info})

        return info

    def match_data(self, kt_type: int) -> dict:
        """
        一种粗糙的方法，直接复制body
        数据链接：
        https://app.jiucaishuo.com/pagesA/tool/fear_greed_gf?kt_type=3
        :param kt_type:
        :return:
        """
        act_time = int(time.time() * 1000)
        payloads = {
            2: {"kt_type": "2", "type": "h5", "version": "2.2.8", "ss": "", "act_time": act_time, "tirgkjfs": "67",
                "abiokytke": "63", "u54rg5d": "ed", "kf54ge7": "2", "tiklsktr4": "7", "lksytkjh": "5445",
                "sbnoywr": "72", "bgd7h8tyu54": "95", "y654b5fs3tr": "a", "bioduytlw": "4", "bd4uy742": "5",
                "h67456y": "754", "bvytikwqjk": "95", "ngd4uy551": "54", "bgiuytkw": "ea", "nd354uy4752": "5",
                "ghtoiutkmlg": "a8f", "bd24y6421f": "2e", "tbvdiuytk": "7", "ibvytiqjek": "5c", "jnhf8u5231": "ea",
                "fjlkatj": "ed2", "hy5641d321t": "e5", "iogojti": "e", "ngd4yut78": "8f", "nkjhrew": "5",
                "yt447e13f": "4", "n3bf4uj7y7": "4", "nbf4uj7y432": "63", "yi854tew": "75", "h13ey474": "752",
                "quikgdky": "1f"},
            3: {"kt_type": "3", "type": "h5", "version": "2.2.8", "ss": "", "act_time": act_time, "tirgkjfs": "07",
                "abiokytke": "d4", "u54rg5d": "e4", "kf54ge7": "b", "tiklsktr4": "7", "lksytkjh": "0e9e",
                "sbnoywr": "1c", "bgd7h8tyu54": "f8", "y654b5fs3tr": "c", "bioduytlw": "a", "bd4uy742": "9",
                "h67456y": "a0e", "bvytikwqjk": "f8", "ngd4uy551": "0e", "bgiuytkw": "6e", "nd354uy4752": "5",
                "ghtoiutkmlg": "cb1", "bd24y6421f": "cc", "tbvdiuytk": "a", "ibvytiqjek": "81", "jnhf8u5231": "6e",
                "fjlkatj": "e4f", "hy5641d321t": "c9", "iogojti": "c", "ngd4yut78": "b1", "nkjhrew": "9",
                "yt447e13f": "1", "n3bf4uj7y7": "e", "nbf4uj7y432": "d4", "yi854tew": "d5", "h13ey474": "d5b",
                "quikgdky": "3c"},
            4: {"kt_type": "4", "type": "h5", "version": "2.2.8", "ss": "", "act_time": act_time, "tirgkjfs": "59",
                "abiokytke": "f2", "u54rg5d": "5e", "kf54ge7": "7", "tiklsktr4": "9", "lksytkjh": "a72c",
                "sbnoywr": "b3", "bgd7h8tyu54": "cd", "y654b5fs3tr": "1", "bioduytlw": "8", "bd4uy742": "c",
                "h67456y": "da7", "bvytikwqjk": "cd", "ngd4uy551": "a7", "bgiuytkw": "94", "nd354uy4752": "b",
                "ghtoiutkmlg": "1f1", "bd24y6421f": "39", "tbvdiuytk": "d", "ibvytiqjek": "08", "jnhf8u5231": "94",
                "fjlkatj": "5ee", "hy5641d321t": "9c", "iogojti": "9", "ngd4yut78": "f1", "nkjhrew": "c",
                "yt447e13f": "f", "n3bf4uj7y7": "7", "nbf4uj7y432": "f2", "yi854tew": "db", "h13ey474": "db7",
                "quikgdky": "fa"},
            5: {"kt_type": "5", "type": "h5", "version": "2.2.8", "ss": "", "act_time": act_time, "tirgkjfs": "8d",
                "abiokytke": "54", "u54rg5d": "f9", "kf54ge7": "9", "tiklsktr4": "d", "lksytkjh": "5e11",
                "sbnoywr": "28", "bgd7h8tyu54": "dc", "y654b5fs3tr": "c", "bioduytlw": "2", "bd4uy742": "4",
                "h67456y": "a5e", "bvytikwqjk": "dc", "ngd4uy551": "5e", "bgiuytkw": "cf", "nd354uy4752": "3",
                "ghtoiutkmlg": "ccd", "bd24y6421f": "89", "tbvdiuytk": "a", "ibvytiqjek": "c2", "jnhf8u5231": "cf",
                "fjlkatj": "f99", "hy5641d321t": "94", "iogojti": "9", "ngd4yut78": "cd", "nkjhrew": "4",
                "yt447e13f": "7", "n3bf4uj7y7": "e", "nbf4uj7y432": "54", "yi854tew": "83", "h13ey474": "839",
                "quikgdky": "a1"},
            6: {"kt_type": "6", "type": "h5", "version": "2.2.8", "ss": "", "act_time": act_time, "tirgkjfs": "49",
                "abiokytke": "3a", "u54rg5d": "86", "kf54ge7": "f", "tiklsktr4": "9", "lksytkjh": "f462",
                "sbnoywr": "d2", "bgd7h8tyu54": "a1", "y654b5fs3tr": "8", "bioduytlw": "3", "bd4uy742": "8",
                "h67456y": "7f4", "bvytikwqjk": "a1", "ngd4uy551": "f4", "bgiuytkw": "4b", "nd354uy4752": "8",
                "ghtoiutkmlg": "837", "bd24y6421f": "2a", "tbvdiuytk": "7", "ibvytiqjek": "ba", "jnhf8u5231": "4b",
                "fjlkatj": "864", "hy5641d321t": "a8", "iogojti": "a", "ngd4yut78": "37", "nkjhrew": "8",
                "yt447e13f": "8", "n3bf4uj7y7": "4", "nbf4uj7y432": "3a", "yi854tew": "88", "h13ey474": "88f",
                "quikgdky": "52"},
            7: {"kt_type": "7", "type": "h5", "version": "2.2.8", "ss": "", "act_time": act_time, "tirgkjfs": "5e",
                "abiokytke": "4e", "u54rg5d": "d0", "kf54ge7": "7", "tiklsktr4": "e", "lksytkjh": "2b0b",
                "sbnoywr": "bf", "bgd7h8tyu54": "1c", "y654b5fs3tr": "7", "bioduytlw": "5", "bd4uy742": "6",
                "h67456y": "22b", "bvytikwqjk": "1c", "ngd4uy551": "2b", "bgiuytkw": "02", "nd354uy4752": "f",
                "ghtoiutkmlg": "7a4", "bd24y6421f": "f5", "tbvdiuytk": "2", "ibvytiqjek": "46", "jnhf8u5231": "02",
                "fjlkatj": "d05", "hy5641d321t": "56", "iogojti": "5", "ngd4yut78": "a4", "nkjhrew": "6",
                "yt447e13f": "7", "n3bf4uj7y7": "b", "nbf4uj7y432": "4e", "yi854tew": "0f", "h13ey474": "0f7",
                "quikgdky": "d4"},
            8: {"kt_type": "8", "type": "h5", "version": "2.2.8", "ss": "", "act_time": act_time, "tirgkjfs": "47",
                "abiokytke": "6d", "u54rg5d": "d3", "kf54ge7": "8", "tiklsktr4": "7", "lksytkjh": "5b0d",
                "sbnoywr": "a4", "bgd7h8tyu54": "62", "y654b5fs3tr": "d", "bioduytlw": "5", "bd4uy742": "1",
                "h67456y": "55b", "bvytikwqjk": "62", "ngd4uy551": "5b", "bgiuytkw": "82", "nd354uy4752": "8",
                "ghtoiutkmlg": "d9b", "bd24y6421f": "4d", "tbvdiuytk": "5", "ibvytiqjek": "1d", "jnhf8u5231": "82",
                "fjlkatj": "d3f", "hy5641d321t": "d1", "iogojti": "d", "ngd4yut78": "9b", "nkjhrew": "1",
                "yt447e13f": "1", "n3bf4uj7y7": "b", "nbf4uj7y432": "6d", "yi854tew": "68", "h13ey474": "688",
                "quikgdky": "cc"},
        }
        return payloads.get(kt_type)

    def industry(self, kt_type: BaseTypeEnum = IndustryEnum.JG, is_full: bool = True) -> Optional[Dict]:
        """
        获取韭圈儿的行业估值数据
        :param kt_type:
        :param is_full:
        :return:
        """
        _url = 'https://api.jiucaishuo.com/v2/kjtlother/getbasedata'
        # act_time = int(time.time()*1000)
        # version = "2.2.7"
        # json_data = {
        #     "kt_type": str(kt_type.dk_value),
        #     "type": "h5",
        #     "version": version,
        #     "ss": "",
        #     "act_time": act_time
        # }
        json_data = self.match_data(kt_type)
        try:
            resp = rpost_json(_url, json=json_data)
        except (XJSONDecodeError, RJSONDecodeError) as e:
            raise CrawlerException(f'对方反爬机制导致错误{e}，请稍候重试……') from e
        info = None
        if resp and resp.get('code') == 0:
            data = resp.get('data')
            kt_flag = kt_type.dk_name
            kt_label = kt_type.label
            crt = data.get('current_time')
            status_str = data.get('status_str')
            num = data.get('num')
            if is_full:
                info = {
                    'current_time': crt,
                    'name': kt_label,
                    'num': num,
                    'status_str': status_str,
                    'kt_flag': kt_flag,
                    'list': data.get('list'),
                    'desc': data.get('desc'),
                }
            else:
                info = {
                    'current_time': crt,
                    'name': kt_label,
                    'num': num,
                    'kt_flag': kt_flag,
                    'status_str': status_str
                }
        return info

    def emotion(self, is_full: bool = True) -> Optional[Dict]:
        """
        恐惧贪婪指数+指数情绪值
        :param is_full:
        :return:
        """
        kjtl_info = self.kjtl(is_full=is_full)
        industry_info = list()
        for industry_enum in IndustryEnum:
            industry_item = self.industry(kt_type=industry_enum, is_full=is_full)
            industry_info.append(industry_item)
        result = {
            'kjtl': kjtl_info,
            'industry': industry_info,
        }
        logger.info(f'{result}')
        return result

    def fed(self, year: int = 10, category_type: str = 'cz', pe_category: str = 'fed') -> Optional[Dict]:
        """
        股债利差
        :param year:
        :param category_type:
        :param pe_category:
        :return:
        """
        fed_url = 'https://api.jiucaishuo.com/v2/guzhi/fedshowbasedata'
        act_time = int(time.time() * 1000)
        try:
            json_data = {"category_type": category_type, "pe_category": pe_category, "region": "", "year": year,
                         "type": "pc",
                         "version": "2.2.7", "authtoken": "", "act_time": act_time, "tirgkjfs": "25",
                         "abiokytke": "6e", "u54rg5d": "bb", "kf54ge7": "a", "tiklsktr4": "5", "lksytkjh": "e018",
                         "sbnoywr": "17", "bgd7h8tyu54": "cb", "y654b5fs3tr": "4", "bioduytlw": "a", "bd4uy742": "5",
                         "h67456y": "7e0", "bvytikwqjk": "cb", "ngd4uy551": "e0", "bgiuytkw": "50", "nd354uy4752": "1",
                         "ghtoiutkmlg": "46c", "bd24y6421f": "7a", "tbvdiuytk": "7", "ibvytiqjek": "d0",
                         "jnhf8u5231": "50", "fjlkatj": "bb8", "hy5641d321t": "a5", "iogojti": "a", "ngd4yut78": "6c",
                         "nkjhrew": "5", "yt447e13f": "0", "n3bf4uj7y7": "0", "nbf4uj7y432": "6e", "yi854tew": "61",
                         "h13ey474": "61a", "quikgdky": "1a"}
            resp = rpost_json(fed_url, json=json_data)
            # FIXME: get error
        except (XJSONDecodeError, RJSONDecodeError) as e:
            raise CrawlerException(f'对方反爬机制导致错误{e}，请稍候重试……') from e
        logger.info(f'=========={resp}=====')
        if resp and resp.get('code') == 0:
            data = resp.get('data')
            return data


class FundFeeRatio(ratio.BaseRatio):

    @retry(exceptions=(XJSONDecodeError, RJSONDecodeError, CrawlerException),
           tries=5,
           delay=0.5,
           backoff=2,
           jitter=(0.3, 0.7),
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
        # [httprequest - Python Request Post with param data - Stack Overflow]
        # (https://stackoverflow.com/questions/15900338/python-request-post-with-param-data)
        try:
            resp = rpost_json(_url, json=data)
        except (XJSONDecodeError, RJSONDecodeError) as e:
            msg = f'基金编码：{fund_code} 反爬机制导致错误：{str(e)}，请稍候重试……'
            logger.error(msg)
            raise CrawlerException(msg) from e

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
                except (ValueError, ParseError, IsClosedDurationError) as e:
                    raise CrawlerException(f'基金 {fund_code} 处理赎回信息 {redeem} 出错！') from e

            if to_db:
                if purchase_info:
                    self.save_fee_info(fund_code, purchase_info, fee_type=settings.FeeTypeEnum.purchase)
                if redeem_info:
                    try:
                        self.save_fee_info(fund_code, redeem_info, fee_type=settings.FeeTypeEnum.redeem)
                    except (TypeError, ParseError) as e:
                        raise CrawlerException(f'基金 {fund_code} 保存赎回信息 {redeem_info} 出错，出错信息：{e}！') from e

            info = {
                'purchase': purchase_info,
                'op': op,
                'redeem': redeem_info,
            }
            return info


jq_app = FundDB()
jq_fr = FundFeeRatio()
if __name__ == '__main__':
    # print(jq_app.kjtl(is_full=True))
    # print(jq_app.industry(is_full=True))
    for item in IndustryEnum:
        result = jq_app.industry(kt_type=item, is_full=False)
        print(result)
        if not result:
            break
    # ratio = jq_fr.rate('001718')
    # print(ratio)

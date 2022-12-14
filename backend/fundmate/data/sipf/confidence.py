#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
原始数据：http://www.sipf.com.cn/dcpj/xxzs/index.shtml
https://www.sipf.com.cn/survey/pc/query/confidence
文件链接：
https://www.sipf.com.cn/survey/sipf-api/v2/download/investor/index?filename=b48892f95ffb4c21819a5f06b99bfd48.pdf&\
originalName=%E6%9C%88%E5%BA%A6%E8%AF%81%E5%88%B8%E6%8A%95%E8%B5%84%E8%80%85%E4%BF%A1%E5%BF%83%E8%B0%83%E6%9F%A\
5%E4%B8%93%E6%8A%A5%EF%BC%882022%E5%B9%B4%E7%AC%AC7%E6%9C%9F+%E6%80%BB%E7%AC%AC172%E6%9C%9F%EF%BC%89.pdf
"""
from typing import Dict, Optional
from urllib import parse

import pendulum
from xalpha.cons import rget_json

from backend.fundmate import utils
from backend.fundmate.data.utils import base as dt_utils


confidence_explanation = '''为了解我国证券投资者在当前经济和市场环境下的投资心理和预期变化，2008 年 4 月，投保基金公司在借鉴国内外投资者信心理论研究和\
调查工作实践的基础上，自主编制证券投资者信心指数，该指数以投保基金公司证券投资者固定样本库为依托编制，以月度为单位对证券投资者信心进行描述。\
为提升指数的科学性和代表性，投保基金公司于 2021 年对指数编制方案进行了修订，自 2022 年 8 月起发布修订后指数。
投保基金公司个人和机构投资者固定样本库约 1.3 万人，通过分层多阶段（PPS）抽样方法从全国范围抽取产生，\
按照样本属性分布将样本库平均分为 12 个子样本组，每月邀请其中三组样本填答问卷，12 个样本组滚动轮换参与调查。\
证券投资者信心指数数值介于 0-100 之间，50 为中性值。指数大于 50 时，表示投资者中持乐观、积极看法的比例大于持悲观、消极看法的比例，\
投资者信心整体偏向乐观。\
指数值越高，表示投资者的信心越强。指数小于 50 时，表示投资者中持乐观、积极看法的比例小于持悲观、消极看法的比例，投资者信心整体偏向悲观。
'''
header_str = '''Accept: application/json, text/plain, */*
Accept-Encoding: gzip, deflate, br
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6
Connection: keep-alive
Cookie: Hm_lvt_2408d8665655cedb52ad993c8468d590=1665666063,1665668594; Hm_lpvt_2408d8665655cedb52ad993c8468d590=1665668594
DNT: 1
Host: www.sipf.com.cn
Referer: https://www.sipf.com.cn/survey/pc/query/confidence
sec-ch-ua: "Chromium";v="106", "Microsoft Edge";v="106", "Not;A=Brand";v="99"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "Windows"
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.42
'''  # noqa:B950


class Confidence:
    """
    投资者信心
    """
    pdf_base_url = 'https://www.sipf.com.cn/survey/sipf-api/v2/download/investor/index'
    _data_url = 'https://www.sipf.com.cn/survey/sipf-api/v2/investor/index'
    source_link = 'https://www.sipf.com.cn/survey/pc/query/confidence'

    def __init__(self):
        self.headers = dt_utils.parse_headers(header_str)

    def full_chart_data(self, endpoint: str = '/chart') -> Optional[Dict]:
        _url = self._data_url + endpoint
        resp = rget_json(_url, headers=self.headers)
        if resp and resp.get('code') == 0:
            return resp
        return None

    def detail_of_month(self, year: Optional[int] = 2022, month: Optional[int] = 6) -> Optional[Dict]:
        """
        获取单月数据
        :param year: 年份
        :param month: 月份
        :return:
        """
        params = {
            'dataYear': year,
            'dataMonth': month
        }
        resp = rget_json(self._data_url, headers=self.headers, params=params)
        if resp and resp.get('code') == 0:
            # 组装下载链接
            data = resp.get('data')
            for mon_info in data:
                filename = mon_info.get('filename')
                original_name = mon_info.get('originalName')
                params = {
                    'filename': filename,
                    'originalName': original_name,
                }
                params_url_encode = parse.urlencode(params)
                full_name = f'{self.pdf_base_url}?{params_url_encode}'
                mon_info['download'] = full_name
            return resp
        return None

    def latest_info(self, is_full: bool = True) -> Dict:
        previous_4_months = utils.first_day_of_previous_n_months(is_strict=False, months=4)
        p_date = pendulum.parse(previous_4_months)
        year, month = p_date.year, p_date.month
        confidence_result = self.detail_of_month(year=year, month=month)
        if confidence_result:
            data = confidence_result.get('data')
            if not is_full:
                new_info = data[0]
                _result = {
                    'base': new_info.get('base'),
                    'buy': new_info.get('buy'),
                    'dataMonth': new_info.get('dataMonth'),
                    'dataYear': new_info.get('dataYear'),
                    'financial': new_info.get('financial'),
                    'fundamental': new_info.get('fundamental'),
                    'market': new_info.get('market'),
                }
                details = [_result]
            else:
                details = data
        else:
            details = None
        _result = {
            'href': self.source_link,
            'details': details
        }
        return _result


if __name__ == '__main__':
    confidence = Confidence()
    result = confidence.detail_of_month(2022, 6)
    full_data = confidence.full_chart_data()
    result1 = confidence.latest_info()
    print(result)
    print(full_data)
    print(result1)

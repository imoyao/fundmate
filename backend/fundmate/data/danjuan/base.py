#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/6/8 17:40
from xalpha.cons import rget_json
from backend.fundmate.data import utils as dt_utils

"""
https://www.jisilu.cn/question/abstract/310234#!answer_3709513
具体指标查询网址
TTM等权市盈率：https://legulegu.com/stockdata/a-ttm-lyr
股债利差：https://danjuanapp.com/valuation-table/jiucai
集思录温度计：https://www.jisilu.cn/data/indicator/
有知有行温度计：https://youzhiyouxing.cn/thermometer

股债利差就是：用股票预期收益率减去十年国债收益率得到的差值（股票 - 债券）。

数值越大代表此时买股票性价比越高于买债券。

通常认为股债利差>3时，市场股票低估适合买入。
"""
header_str = '''Accept: application/json, text/plain, */*
Accept-Encoding: gzip, deflate, br
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7
Connection: keep-alive
Cookie: device_id=web_H1rTlL64qu; xq_a_token=aa8cf5aa25e1e9dd1cb237236a8bec27242760bf; Hm_lvt_d8a99640d3ba3fdec41370651ce9b2ac=1622623735,1622625108,1623045004; acw_tc=2760778916231451543431366e8e1c2515e2724de5101def82af28c6d920e0; channel=1500012085; Hm_lpvt_d8a99640d3ba3fdec41370651ce9b2ac=1623145825; timestamp=1623145824959
DNT: 1
elastic-apm-traceparent: 00-dd761310377a09f702d0df61ae45900c-ed908de0729027eb-01
Host: danjuanfunds.com
Referer: https://danjuanfunds.com/screw/valuation-table?channel=1500012085
sec-ch-ua: " Not;A Brand";v="99", "Microsoft Edge";v="91", "Chromium";v="91"
sec-ch-ua-mobile: ?0
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36 Edg/91.0.864.41
'''


class DanJuan:
    channel_list = ['jiucai', 'lsd']

    def get_evl(self, url):
        hd = dt_utils.parse_headers(header_str)
        resp = rget_json(url, headers=hd)
        return resp

    def get_detail(self, channel=None):
        assert channel in self.channel_list
        url = f'https://danjuanapp.com/djapi/fundx/activity/user/vip_valuation/show/detail?source={channel}'
        return self.get_evl(url)

    def eval_val(self):
        """
        抓取全部信息
        :return:
        """
        info = dict()
        for channel in self.channel_list:
            item = self.get_detail(channel)
            info[channel] = item
        import json
        return json.dumps(info)

    def overview(self):
        """
        只显示概要信息
        :return:
        """
        pass


dj = DanJuan()
if __name__ == '__main__':
    print(dj.eval_val())

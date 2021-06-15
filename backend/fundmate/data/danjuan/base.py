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
import cachetools.func
from xalpha.cons import rget_json
from typing import Union

from backend.fundmate.data import utils as dt_utils
from backend.fundmate import utils

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
    """
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

    def get_detail(self, channel: Union[str, None] = None):
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

    def eval_val(self, is_overview: bool = False):
        """
        抓取信息
        :return:
        """
        info = dict()
        for channel in self.CHANNEL_LIST:
            item = self.get_detail(channel)
            if is_overview:
                data = item.get('data')
                data.pop('spread_trends')
                item['data'] = data
            info[channel] = item
        return info

    @cachetools.func.ttl_cache(maxsize=128, ttl=utils.seconds_today_leaves())
    def overview(self):
        """
        只显示概要信息
        :return:
        """
        _info = self.eval_val(is_overview=True)
        return _info


dj = DanJuan()
if __name__ == '__main__':
    print(dj.overview())

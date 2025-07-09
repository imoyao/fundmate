#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/7/15 17:37
"""基金经理排名
1. 聪明投资者
2. 蛋卷名人堂
"""
from xalpha.cons import rget_json

from backend.fundmate import utils
from backend.fundmate.data.utils import base as dt_utils


class FundManager:
    """
    爬取各种基金经理排名，将其写入数据库
    """
    CT_HEADER_STR = '''Accept: application/json, text/plain, */*
DNT: 1
Referer: https://www.cmtzz.cn/
sec-ch-ua: " Not;A Brand";v="99", "Microsoft Edge";v="91", "Chromium";v="91"
sec-ch-ua-mobile: ?0
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 \
Safari/537.36 Edg/91.0.864.70
'''

    def cmtzz(self):
        """聪明投资者
        url: https://www.cmtzz.cn/top-managers

        {'朱少醒': {
            'TopProdReturnManA': 22.53,
             'content': {'route': '/article/45971',
                         'title': '一季报|中字头港股受青睐，朱少醒大笔加仓韦尔，刘彦春成千亿顶流，白酒持仓近300亿，周蔚文继续增持航空股'},
             'danjuan': True,
             'departure': '',
             'image': 'https://cdn.cmtzz.cn/sites/default/files/2020-07/朱少醒_0.jpg',
             'nid': 12624,
             'route': '/staff/12624',
             'scale': 37995519405.36,
             'tags': ['均衡配置', '成长特色鲜明', '少择时', '换手率低'],
             'workingDay': 18
             }
         ……
        }
        :return:
        """
        _desc = '''立足于长期：选择管理时间超过3年的现役基金经理，引导长期投资理念；

基金绩效评价：以投资收益为基础，全面考察基金经理所管理所有产品业绩、考察不同时间段的收益情况；

多维度权重：对不同时间段的业绩表现赋予不同的权重，权重按业绩时间长短做递减；

管理人能力评价：结合管理规模、风格稳定性、投研水平、投资管理流程等进行更深度考察；
参阅 [聪明投资者TOP30基金经理筛选方法和指标|聪明投资者](https://www.cmtzz.cn/article/30118)
        '''  # noqa:F841
        _info = self.cmtzz_info()
        _detail = self.ct_detail()

        _mgr_list, _data = None, None
        if _info.get('code') == 0:
            _data = _info.get('data')
        if _detail.get('code') == 0:
            _mgr_list = _detail.get('data').get('list')

        if _mgr_list and _data:
            result = utils.merge_iterables_of_dict('title', _mgr_list, _data)
            return dict(result)

    def cmtzz_info(self):
        """
        {
         'title': '朱少醒'         # 名称
         'image': 'https://cdn.cmtzz.cn/sites/default/files/2020-07/朱少醒_0.jpg',     # 头像
         'route': '/staff/12624',           # 详情页
        'content': {
             'route': '/article/45971',     # 介绍文章
             'title': '一季报|中字头港股受青睐，朱少醒大笔加仓韦尔，刘彦春成千亿顶流，白酒持仓近300亿，周蔚文继续增持航空股'
             },
         'danjuan': True,
         'departure': '',
         'tags': ['均衡配置', '成长特色鲜明', '少择时', '换手率低'], # 标签
         }

        :return:
        """
        _url = 'https://api.cmtzz.cn/api/v2/staffs/tops'
        hd = dt_utils.parse_headers(self.CT_HEADER_STR)
        resp = rget_json(_url, headers=hd)
        return resp

    def ct_detail(self):
        """
        {
         'nid': 12624,
         'title': '朱少醒',        # 名称
         'TopProdReturnManA': 22.53, # 任职年化收益
         'scale': 37995519405.36,   # 管理基金总规模
         'workingDay': 18}          # 累计任职时间（年）

        :return:
        """
        _url = 'https://api.cmtzz.cn/api/v1/fund-managers'
        hd = dt_utils.parse_headers(self.CT_HEADER_STR)
        resp = rget_json(_url, headers=hd)
        return resp

    def djmrt(self):
        """
        都是图片，如何抓取？
        只能获取媒体报导链接
        [蛋卷基金名人堂](https://danjuanfunds.com/activity/warband-team/jjmrt)
        :return:
        """
        pass


if __name__ == '__main__':
    fm = FundManager()
    print(fm.cmtzz())

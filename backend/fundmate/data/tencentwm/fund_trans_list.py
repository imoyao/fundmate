#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Administrator at 2021/12/30 22:27
"""
每次更新数据时需要去网站获取新的key并设置到`.env`环境中
"""
import time

import dateparser
import pyjson5
from xalpha.cons import rget

from backend.fundmate import settings, utils
from backend.fundmate.data import utils as dt_utils

env = settings.env

url = 'https://www.tencentwm.com/app/v2.0/wxh5_fund_trans_list.cgi'
# 每次更新
g_tk = env.str('TENCENTWM_G_TK')
qlskey = env.str('TENCENTWM_QLS_KEY')
# 用户特征码，只更新一次
qluin = env.str('TENCENTWM_QLUIN')
REQUEST_STR = f'''accept: text/plain, */*; q=0.01
accept-encoding: gzip, deflate, br
accept-language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7
dnt: 1
referer: https://www.tencentwm.com/web/v3/account/trans_detail.shtml
connection: keep-alive
cookie: qluin={qluin}; qlskey={qlskey}
user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36 Edg/91.0.864.54 '''
headers = dt_utils.parse_headers(REQUEST_STR)


def get_trans_detail():
    result = list()
    page = 0
    acc_time = None
    while True:
        if not acc_time:
            acc_time = str(dateparser.parse(str(time.time())))
        offset = 20 * page
        print(offset, acc_time)
        params = {
            'pur_type': 'all',
            'offset': offset,
            'acc_time': acc_time,
            'g_tk': g_tk,
        }
        resp = rget(url, headers=headers, params=params)
        if resp:
            page += 1
            ret_str = resp.content.decode('utf-8')
            data = pyjson5.loads(ret_str)
            ret_code = data.get('retcode')
            if ret_code == '0':
                item = data.get('Array')
                acc_time = data.get('acc_time')
                result.extend(item)
            else:
                # 265800010
                print(ret_code, data)
                break

    utils.write_json_data(result, f'./test.json')


if __name__ == '__main__':
    get_trans_detail()

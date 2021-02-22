#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/2/21 10:49
"""
交银双息和泰康汇选悦泰的收益对比
"""
import json
import time

import pandas
import requests
import xalpha as xa

tk_code = 'TK1001'
page_num = 20


def get_info():
    # base_url = f'http://dq.jd.com/pension/item/netValueDetail?pageNo={page_num}&fundCode={tk_code}'
    req_url = f'http://dq.jd.com/pension/item/netValueDetail?pageNo=1&fundCode={tk_code}'
    start_data = do_get(req_url)
    pager = start_data.get('result').get('pager')
    total_page = pager.get('totalPage')
    data = []
    # print(type(total_page))
    # total_page = 1
    for i in range(1, total_page + 1):
        base_url = f'http://dq.jd.com/pension/item/netValueDetail?pageNo={i}&fundCode={tk_code}'
        ret = do_get(base_url)
        result = ret.get('result').get('resVo')
        for item in result:
            date = item.get('netValueDate')
            val = item.get('netValue')
            info = {'date': date, 'val': val}
            data.append(info)
        time.sleep(.3)
    with open(f'./{tk_code}.json', 'w') as f:
        json.dump(data, f)
    print(data)
    return data


def do_get(url):
    r = requests.get(url=url)
    ret = r.json()
    return ret


def get_tk_val():
    ret = list(pandas.read_json(path_or_buf='TK1001.json', orient='records').val)[::-1]
    print(len(ret))
    return ret


def jy_val():
    ret = list(xa.get_daily('F519732', start='2017-08-16', end='2021-02-19').close)
    print(len(ret))
    return ret


def cal(val_list):
    per_count = 10000 / val_list[0]
    print(f'buy count:{per_count},start:{val_list[0]},end:{val_list[-1]}')
    ret_start = 0
    for j in val_list:
        item_val = per_count * j-10000
        # print(item_val)
        if item_val > 0:
            ret_start += item_val
        else:
            ret_start -= item_val
        # print(f'jy:{item_b}')
    print(f'jy-------:{ret_start}')
    return item_val


if __name__ == '__main__':
    tk_list = get_tk_val()
    jy_list = jy_val()
    tk = cal(tk_list)
    jy = cal(jy_list)
    print(f'tk:{tk},jy:{jy}')
    # ret = get_info()
    # print(ret)

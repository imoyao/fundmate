#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
获取费率
"""
import re

from bs4 import BeautifulSoup
from utils import *  # noqa: E403


def _get_fl_table_tag(html):
    soup = BeautifulSoup(html, 'html5lib')
    tbs = soup.find_all('table')
    for tb in tbs:
        name = ' '.join(tb['class'])
        if name == 'w650 comm jjfl' and '赎回费率' in str(tb):
            return tb
    return ''


def parse_fl_table_tag(table_soup):
    data_list = []
    heads = []
    for idx, tr in enumerate(table_soup.find_all('tr')):
        if idx == 0:
            ths = tr.find_all('th')
            for th in ths:
                heads.append(th.contents[0])
        elif idx != 0:
            tds = tr.find_all('td')
            li = {}
            for td in tds:
                li.update({heads[len(li)]: td.contents[0]})
            li.pop('适用金额')
            data_list.append(li)
    return data_list


def _get_fl_url(code):
    return 'http://fundf10.eastmoney.com/jjfl_%s.html' % code


def _fl_table_parser(fl_table):
    fls = []
    for item in fl_table:
        date = item['适用期限']
        fl_p = item['赎回费率']
        fl = float(fl_p.replace('%', ''))

        years = re.findall(r"(\d+)年", date)
        for i in years:
            date = date.replace(i + '年', '%d天' % (int(i) * 365), 1)

        xydy = 0
        if '小于等于' in date:
            xydy = 1
            date = date.replace('小于等于', '小于')

        days = re.findall(r"小于(\d+)天", date)
        if not days:
            continue
        fls.append((int(days[0]) + xydy, fl))
    fl_p = fl_table[-1]['赎回费率']
    fl = float(fl_p.replace('%', ''))
    fls.append((float('inf'), fl))
    return fls


def get_fl_table(code):
    """
    赎回费率表爬取
    :param code: 
    :return:
    """
    code = str(code).zfill(6)
    url = _get_fl_url(code)
    html = get_resonse(url)
    t = _get_fl_table_tag(html)
    d = parse_fl_table_tag(t)
    fl_table = _fl_table_parser(d)
    return fl_table


if __name__ == "__main__":
    codes = [924]
    for i in codes:
        r = get_fl_table(i)
        print(r)

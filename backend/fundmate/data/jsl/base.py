#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/6/10 11:43
import re
from pathlib import Path

import cachetools.func
from xalpha.cons import rget, rget_json

from backend.fundmate import excepts as dt_except
from backend.fundmate import utils
from backend.fundmate.data.utils import base as dt_utils
from backend.fundmate.exts.flask_loguru import logger

url = 'https://www.jisilu.cn/data/indicator/get_last_indicator/'
REQUEST_STR = """Accept: application/json, text/javascript, */*; q=0.01
Accept-Encoding: gzip, deflate, br
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7
Connection: keep-alive
Content-Length: 0
Cookie: kbzw_r_uname=%E8%A5%BF%E9%A3%8E%E4%B8%8D%E7%98%A6; kbz_newcookie=1; kbzw__Session=a295sqg2agsgc6dqgd786nk613;""" \
              """Hm_lvt_164fe01b1433a19b507595a43bf58262=1622536736,1622596667,1622686815,1623044428;""" \
              """kbzw__user_login=7Obd08_P1ebax9aXXwc1ShoFVzDuV_kamrCW6c3q1e3Q6dvR1YyglaSx25mv0trD15nZ3KTbwqHG16""" \
              """mqmbKirpfbw9nb2Jmcndbd3dPGpJ-pm6uSqJiupbaxv9Gkwtjz1ePO15CspaOYicfK4t3k4OyMxbaWkqelo7OBx8rir6m""" \
              """kmeStlp-BuOfj5MbHxtbE3t2ooaqZpJStl5vDqcSuwKWV1eLX3IK9xtri4qGBs8nm6OLOqKWokKaPq6uqqo-nmJTM1s""" \
              """_a3uCRq5SupaaugbXF26iumqecpZqslaWrpA..;""" \
              """Hm_lpvt_164fe01b1433a19b507595a43bf58262=1623296705
DNT: 1
Host: www.jisilu.cn
Origin: https://www.jisilu.cn
Referer: https://www.jisilu.cn/
sec-ch-ua: " Not;A Brand";v="99", "Microsoft Edge";v="91", "Chromium";v="91"
sec-ch-ua-mobile: ?0
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77""" \
              """ Safari/537.36 Edg/91.0.864.41
X-Requested-With: XMLHttpRequest
"""
current_path = Path(__file__).parent.resolve()


class JSL:
    """
    说明：
    1. 温度计的基本含义，请参考帖子 https://www.jisilu.cn/question/68925。
    2. PB/PE中值基于A股全市场中的PB/PE中位数，扣除停牌股、1年内的新股、ST股票等；需要有一定样本数中位数才有意义（比如>100)，因此选择1994-09-29为PB/PE中位数的起点。
    3. 以当前PB/PE中值在历史序列中的百分位来刻度温度计，如果历史序列样本太少，其波动将非常剧烈，参考意义较小，比如本图中的初期；为了在计算温度的时候有一定的历史序列样本（比如>三个月），选择1995-01-02为温度计的起点。
    4. PE中值收益率 = 1/PE中值 * 100%。
    5. 全市场的代表指数，2005-01-04之前以上证指数表示，之后以中证全指表示。
    """

    @staticmethod
    @cachetools.func.ttl_cache(maxsize=128, ttl=utils.seconds_today_leaves())
    def overview() -> dict:
        """
        集思录温度计
        带有缓存功能：每天只获取一次，see also: https://stackoverflow.com/a/54357155
        :return:
        """
        hd = dt_utils.parse_headers(REQUEST_STR)
        resp = rget_json(url, headers=hd)
        return resp

    @staticmethod
    def more_details(readable=True) -> dict:
        """
        该页面显示的数据：https://www.jisilu.cn/data/indicator/
        :return:
        """
        html_fp = f'{current_path}/temp.html'
        json_fp = f'{current_path}/jsl.json'
        p = Path(html_fp)
        # 文件过期则删除重爬
        dt_utils.delete_overdue(html_fp, json_fp)

        if not p.exists():
            hd = dt_utils.parse_headers(REQUEST_STR)
            resp = rget('https://www.jisilu.cn/data/indicator/', headers=hd)
            with open(html_fp, 'w') as f:
                """
                see also: python爬虫抓下来的网页，中间的中文乱码怎么解决？ - 菜鸟分析的回答 - 知乎
https://www.zhihu.com/question/36938733/answer/573224207
                """
                resp.encoding = resp.apparent_encoding
                text = resp.text
                f.write(text)
        else:
            with open(html_fp) as f:
                text = f.read()

        reg_mat = re.findall(r'var (.*) = (.*);', text)
        info = dict()
        if reg_mat:
            # 索引名称（A股全市场） 10年国债收益率均值 交易日期
            useful_key = ['index_nm', 'avg_base_ytm', '__date']
            info = dict()
            for item in reg_mat:
                key = item[0]
                if key in useful_key:
                    if key == '__date':
                        key = 'date'
                    info[key] = eval(item[1])
        """
        PE中值 PE温度 股票数量 IPO数量 ST数量 A股全市场指数点位
        """
        data_useful_key = ['median_PE', 'median_PE_t', 'stock_count', 'IPO_count', 'st_count', 'index_point']
        float2int_iter = ['stock_count', 'IPO_count', 'st_count']
        data_mat = re.findall(r'\t(.*):\t*(\[.*]),', text)
        if data_mat:
            _data = dict()
            for item in data_mat:
                key = item[0]
                val = eval(item[1])
                if key in data_useful_key:
                    if key in float2int_iter:
                        val = [int(v) for v in val]
                    _data[key.lower()] = val
            info['data'] = _data
            median_pe_l = _data.get('median_pe')
            median_pe_t_l = _data.get('median_pe_t')
            stock_count_l = _data.get('stock_count')
            ipo_count_l = _data.get('ipo_count')
            st_count_l = _data.get('st_count')
            index_point_l = _data.get('index_point')

            if readable:
                date = info.get('date')
                avg_base_ytm = info.get('avg_base_ytm')
                read_data = dict()
                new_list = list()
                ret = dict()
                mid = map(list,
                          zip(date, median_pe_l, median_pe_t_l, stock_count_l, ipo_count_l, st_count_l, index_point_l))
                for item in mid:
                    new_dict = dict(
                        zip(['date', 'median_pe', 'median_pe_t', 'stock_count', 'ipo_count', 'st_count', 'index_point'],
                            item))
                    new_list.append(new_dict)
                ret['info'] = new_list
                ret['avg_base_ytm'] = avg_base_ytm
                read_data['data'] = ret
                return read_data

            return info
        logger.warning('JSL temper get Error!')
        raise dt_except.CrawlerException('JSL temper get Error!')

    def qz_info(self, is_full: bool = False, is_more: bool = False) -> dict:
        _href = 'https://www.jisilu.cn/data/indicator/'
        ov = jsl.overview()
        info = dict()
        if ov:
            update_date = ov.get('price_dt')
            temper = ov.get('median_pb_temperature')
            ov.update({'href': _href})
            _data = {'update_date': update_date, 'temper': temper}
            if not is_full:
                info = {'overview': _data}
            else:
                info = {'temper': ov}
            if is_more:
                _more = jsl.more_details()
                info.update({'details': _more})
        return info


jsl = JSL()
if __name__ == '__main__':
    data = jsl.qz_info(is_full=True, is_more=True)
    print(data)

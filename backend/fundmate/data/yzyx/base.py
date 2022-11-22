#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/6/7 14:42
import json
import re
from pathlib import Path
from typing import Union

import pandas as pd
from deprecated import deprecated
from lxml import etree
from xalpha.cons import rget

from backend.fundmate import excepts as dt_except
from backend.fundmate import utils
from backend.fundmate.data.utils import base as dt_utils
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.libs import convert


header_str = '''Host: youzhiyouxing.cn
Connection: keep-alive
Cache-Control: max-age=0
sec-ch-ua: " Not;A Brand";v="99", "Microsoft Edge";v="91", "Chromium";v="91"
sec-ch-ua-mobile: ?0
Upgrade-Insecure-Requests: 1
DNT: 1
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36 Edg/91.0.864.41
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9
Sec-Fetch-Site: same-origin
Sec-Fetch-Mode: navigate
Sec-Fetch-Dest: document
Referer: https://youzhiyouxing.cn/thermometer
Accept-Encoding: gzip, deflate, br
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7
Cookie: _flourish_data=SFMyNTY.g2gDdAAAAAFkAAlkZXZpY2VfaWRtAAAAJGM4MDhkM2YzLTdkZGUtNGEwYi1hODJjLTZlZDg4YmUxNWFiMW4GAELC-uR5AWIAAVGA.xRt-7BqEruLTp87o4zF2WrOEMErTQww_wgQq_rOMiBE; _flourish_key=SFMyNTY.g3QAAAACbQAAAAtfY3NyZl90b2tlbm0AAAAYa3VuV1NFd2RONkhhdkhlUnI1bVROMUZZbQAAAAdyZWZlcmVybQAAACRodHRwczovL3lvdXpoaXlvdXhpbmcuY24vdGhlcm1vbWV0ZXI.DICHDr8U6inf5eLnv8EsGIGkINJBXYLB5XV7b9NVPKc
'''  # noqa :E501
current_path = Path(__file__).parent.resolve()
FILE_NAME = 'temp.html'
FILE_PATH = Path.joinpath(current_path, FILE_NAME)


class YZYX:
    """
    有知有行温度计
    每个交易日晚 8 点，更新当日股市温度 TODO: 增加定时获取功能
    """
    URL = 'https://youzhiyouxing.cn/thermometer'

    def __init__(self):
        self.html_fp = FILE_PATH

    def get_html_text(self, json_fp=None):
        p = Path(self.html_fp)
        # 文件过期则删除重爬
        dt_utils.delete_overdue(self.html_fp, json_fp)

        if not p.exists():
            hd = dt_utils.parse_headers(header_str)
            resp = rget(self.URL, headers=hd)
            with open(self.html_fp, 'w') as f:
                text = resp.text
                f.write(text)
        else:
            with open(self.html_fp) as f:
                text = f.read()
        return text

    def valuations(self, is_df: bool = False) -> Union[dict, pd.DataFrame]:
        """
        指数表解析 FIXME: long time,cache this?
        """
        df_tab = pd.read_html(self.URL)
        if df_tab:
            df = df_tab[1]
            cols = df.columns.tolist()
            rename_cols = ['index_raw_str', 'index_temper', 'interval_rate', 'yield']
            rename_map = dict(zip(cols, rename_cols))
            df.rename(columns=rename_map, inplace=True)
            '''  # noqa
            >>> index_raw_str
            '中证红利  000922.CSI'
            >>> index_raw_str.split(' ')
            ['中证红利', '', '000922.CSI']
            # [python - Pandas FutureWarning: Columnar iteration over characters will be deprecated in future releases - Stack Overflow](https://stackoverflow.com/questions/61313365/pandas-futurewarning-columnar-iteration-over-characters-will-be-deprecated-in-f)
            equals: df['index_name'], _, df['index_code'] = df['index_raw_str'].str.split(' ').str
            '''
            df[['index_name', 'drop_it', 'index_code']] = df['index_raw_str'].str.split(' ', expand=True)
            data = df.drop(columns=['index_raw_str', 'drop_it'])
            if not is_df:
                _info = data.to_dict(orient='records')
                return _info
            return data

    # @show_time
    def daily_temper(self, is_minimal: bool = True, is_full: bool = False) -> dict:
        """
        新版市场温度数据
        :return:
        """
        text = self.get_html_text()
        html = etree.HTML(text)
        update_date_path = '//div[@class="tw-flex tw-justify-between"]/p[1]/text()'
        update_text = html.xpath(update_date_path)[0]
        reg_mat = re.findall(r'：\s*(.+)', update_text)
        update_date = None
        if reg_mat:
            raw_date = reg_mat[0]
            update_date = str(convert.try_parse_date(raw_date))

        # 全市场温度
        temper_div = '//div[@class="tw-flex tw-items-center"]/div/'
        temp_path = f'{temper_div}div/text()'
        temp_text = html.xpath(temp_path)[0]
        temp_digit = re.search(r'(\d+)', temp_text)[0]
        temp_int = None
        if temp_digit:
            temp_int = int(temp_digit)
        temp_desc = f'{temper_div}div[2]/div'
        temp_desc_list = html.xpath(temp_desc)
        temp_desc = [item.text for item in temp_desc_list]
        desc_list = ['eval', 'trend']
        desc_dict = dict(zip(desc_list, temp_desc))
        whole_market_temp = {'temperature': temp_int, 'desc': desc_dict}
        info = {'href': self.URL}
        if is_minimal:
            info['date'] = update_date,
            info.update(whole_market_temp)
        else:
            info.update({
                'date': update_date,
                'whole_market_temper': whole_market_temp,
            })
        if is_full:
            # 指数观察
            _valuations = self.valuations()
            bond_div = '//div[@class="tw-bg-bgd-area tw-text-t-normal tw-rounded-1 tw-mb-3 tw-cursor-pointer"]/ '
            bond_xpath = f'{bond_div}div/p/span/text()'
            bond_temper = html.xpath(bond_xpath)[0]
            ten_ytm_xpath = f'{bond_div}div[2]/p/span/span/text()'
            ten_ytm_rate = html.xpath(ten_ytm_xpath)[0]
            ten_ytm_xpath_update_xp = f'{bond_div}div[2]/label/text()'
            ten_ytm_xpath_update_date = html.xpath(ten_ytm_xpath_update_xp)[0]
            gdp_div = '//div[@class="tw-bg-bgd-area tw-text-t-normal tw-rounded-1 tw-cursor-pointer"]/ '
            gdp_quarter_xp = f'{gdp_div}div/p/span/span/text()'
            gdp_quarter_rate = html.xpath(gdp_quarter_xp)[0]
            gdp_quarter_update_xp = f'{gdp_div}div/label/text()'
            gdp_quarter_update_date = html.xpath(gdp_quarter_update_xp)
            gdp_month_xp = f'{gdp_div}div[2]/p/span/span/text()'
            gdp_month_rate = html.xpath(gdp_month_xp)[0]
            quarter_date, month_date = gdp_quarter_update_date
            macro_data = {
                'bond_temper': bond_temper.strip(),
                'ten_ytm_rate': {
                    'rate': ten_ytm_rate,
                    'update_date': ten_ytm_xpath_update_date.strip()
                },
                'gdp': {
                    'quarter': {
                        'rate': gdp_quarter_rate,
                        'date': quarter_date.strip()
                    },
                    'month': {
                        'rate': gdp_month_rate,
                        'date': month_date.strip()
                    },
                }
            }

            info.update({
                'valuations': _valuations,
                'macro_data': macro_data,
            })
        return info

    @deprecated(version='1.0.0', reason='有知有行旧版网站可以直接在html中正则获取数据，网站已改版')
    def daily_temp_old(self):
        # TODO:typing cause error now see also:[Can't use decorate `@deprecated` with typing? · Issue #6841 ·
        #  sqlalchemy/sqlalchemy](https://github.com/sqlalchemy/sqlalchemy/issues/6841)
        """
        每日温度历史值
        :return:[{"asset_rate": "386.2744", "avg_return_3": null, "close": "765.6346", "date": "2005-01-07",
        "degree": 9, "return_day": "0.002397", "rw_pb": "1.9821"},
     {"asset_rate": "385.8761", "avg_return_3": null, "close": "767.3533", "date": "2005-01-14", "degree": 9,
      "return_day": "-0.011090", "rw_pb": "1.9886",...}]
        """
        """
        {'asset_rate': '2761.9669',
         'avg_return_3': '105.1500',    # 持有3年平均收益率
         'close': '5606.7929',  # 万德全A
         'date': '2021-06-04',
         'degree': 21,      # 温度
         'return_day': '0.005316',
         'rw_pb': '2.0300'}
        """
        json_fp = f'{current_path}/yzyx.json'
        text = self.get_html_text(json_fp=json_fp)

        reg_mat = re.findall(r"const data = parseData\(JSON.parse\('(.*)'\)\)", text)
        if reg_mat:
            _info = reg_mat[0]
            data = json.loads(_info)
            utils.write_json_data(data, json_fp)
            return data
        logger.warning('Get YZYX temperature Error!')
        raise dt_except.CrawlerException('YZYX temperature get Error!')

    def temp_detail(self):
        return self.daily_temp_old()[-1]

    def last(self) -> dict:
        return self.daily_temper()


yzyx = YZYX()

if __name__ == '__main__':
    print(yzyx.daily_temper())

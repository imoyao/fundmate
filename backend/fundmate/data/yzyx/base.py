#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/6/7 14:42
import re
from pathlib import Path
import json
import dateparser

from xalpha.cons import rget
from backend.fundmate.data import utils as dt_utils
from backend.fundmate import excepts as dt_except
from datetime import datetime
from backend.fundmate.exts.flask_loguru import logger

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
'''
current_path = Path.cwd()


class YZYXTemp:
    """
    有知有行温度计
    """

    def daily_temp(self) -> list:
        """
        [{"asset_rate": "386.2744", "avg_return_3": null, "close": "765.6346", "date": "2005-01-07", "degree": 9, "return_day": "0.002397", "rw_pb": "1.9821"}, {"asset_rate": "385.8761", "avg_return_3": null, "close": "767.3533", "date": "2005-01-14", "degree": 9, "return_day": "-0.011090", "rw_pb": "1.9886",...}
        :return:
        """
        '''
        {'asset_rate': '2761.9669', 
     'avg_return_3': '105.1500',    # 持有3年平均收益率
     'close': '5606.7929',  # 万德全A
     'date': '2021-06-04',
     'degree': 21,      # 温度
     'return_day': '0.005316',
     'rw_pb': '2.0300'}
        '''
        today = datetime.today()
        html_fp = f'{current_path}/temp.html'
        json_fp = f'{current_path}/yzyx.json'
        p = Path(html_fp)
        # 文件过期则删除重爬
        df_mt = dateparser.parse(str(p.stat().st_mtime))
        y, m, d = df_mt.year, df_mt.month, df_mt.day
        is_not_overdue = all([y == today.year, m == today.month, d == today.day])
        if not is_not_overdue:
            p.unlink()
            Path(json_fp).unlink()

        if not p.exists():
            hd = dt_utils.parse_headers(header_str)
            resp = rget('https://youzhiyouxing.cn/thermometer', headers=hd)
            with open(html_fp, 'w') as f:
                text = resp.text
                f.write(text)
        else:
            with open(html_fp) as f:
                text = f.read()

        reg_mat = re.findall(r"const data = parseData\(JSON.parse\('(.*)'\)\)", text)
        if reg_mat:
            _info = reg_mat[0]
            data = json.loads(_info)
            with open(json_fp, 'w') as f:
                json.dump(data, f)
            return data
        logger.warning('YZYX temper get Error!')
        raise dt_except.CrawlerException('YZYX temper get Error!')

    def last(self) -> dict:
        return self.daily_temp()[-1]


yzyx_temp = YZYXTemp()

if __name__ == '__main__':
    print(yzyx_temp.last())

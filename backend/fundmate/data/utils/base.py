#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/6/7 14:53
"""
与爬虫、数据处理有关的一些工具方法
"""
import copy
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Union

import dateparser
import yaml

from backend.fundmate import settings
from backend.fundmate.excepts import ParseError, UnpackError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import FeeRatio, Fund, PurchaseRule, RedeemRule


def parse_headers(raw_header: str) -> dict:
    """
    通过原生请求头获取请求头字典
    [请求头转换为字典 - hankleo - 博客园](https://www.cnblogs.com/hankleo/p/10494606.html)
    [Python爬虫：将headers请求头字符串转为字典 - nmydt - 博客园](https://www.cnblogs.com/nmydt/p/14256316.html)
    Examples:
    ```
    header_str = '''Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9
    Accept-Encoding: gzip, deflate, br
    Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7
    Connection: keep-alive
    Cookie: _flourish_data=SFMyNTY.g2gDdAAAAAFkAAlkZXZpY2VfaWRtAAAAJGM4MDhkM2YzLTdkZGUtNGEwYi1hODJjLTZlZDg4YmUxNWFiMW4GAELC-uR5AWIAAVGA.xRt-7BqEruLTp87o4zF2WrOEMErTQww_wgQq_rOMiBE; _flourish_key=SFMyNTY.g3QAAAACbQAAAAtfY3NyZl90b2tlbm0AAAAYa3VuV1NFd2RONkhhdkhlUnI1bVROMUZZbQAAAAdyZWZlcmVybQAAACRodHRwczovL3lvdXpoaXlvdXhpbmcuY24vdGhlcm1vbWV0ZXI.DICHDr8U6inf5eLnv8EsGIGkINJBXYLB5XV7b9NVPKc
    DNT: 1
    Host: youzhiyouxing.cn
    If-None-Match: "464BA6D"
    Referer: https://youzhiyouxing.cn/thermometer
    sec-ch-ua: " Not;A Brand";v="99", "Microsoft Edge";v="91", "Chromium";v="91"
    sec-ch-ua-mobile: ?0
    Sec-Fetch-Dest: image
    Sec-Fetch-Mode: no-cors
    Sec-Fetch-Site: same-origin
    User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36 Edg/91.0.864.41
    '''     # noqa: E501
    parse_headers(header_str)

    {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9', 'Accept-Encoding': 'gzip, deflate, br', 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7', 'Connection': 'keep-alive', 'Cookie': '_flourish_data=SFMyNTY.g2gDdAAAAAFkAAlkZXZpY2VfaWRtAAAAJGM4MDhkM2YzLTdkZGUtNGEwYi1hODJjLTZlZDg4YmUxNWFiMW4GAELC-uR5AWIAAVGA.xRt-7BqEruLTp87o4zF2WrOEMErTQww_wgQq_rOMiBE; _flourish_key=SFMyNTY.g3QAAAACbQAAAAtfY3NyZl90b2tlbm0AAAAYa3VuV1NFd2RONkhhdkhlUnI1bVROMUZZbQAAAAdyZWZlcmVybQAAACRodHRwczovL3lvdXpoaXlvdXhpbmcuY24vdGhlcm1vbWV0ZXI.DICHDr8U6inf5eLnv8EsGIGkINJBXYLB5XV7b9NVPKc', 'DNT': '1', 'Host': 'youzhiyouxing.cn', 'If-None-Match': '"464BA6D"', 'Referer': 'https://youzhiyouxing.cn/thermometer', 'sec-ch-ua': '" Not;A Brand";v="99", "Microsoft Edge";v="91", "Chromium";v="91"', 'sec-ch-ua-mobile': '?0', 'Sec-Fetch-Dest': 'image', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'same-origin', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36 Edg/91.0.864.41'}     # noqa: E501
    ```
    :param raw_header:从浏览器直接复制过来的字符串
    :return:requests使用的字典
    """
    return dict([line.split(": ", 1) for line in raw_header.split("\n") if line != ''])


def paginate(count: int, size: int = 10) -> Generator:
    """
    爬虫爬取时针对页面分页功能
    :param count:总数
    :param size:每页数量
    :return:
    """
    page = 0
    for i in range(0, count, size):
        page += 1
        yield page, size


def delete_overdue(html_fp: Union[str, Path], json_fp: Union[str, Path, None]) -> int:
    """
    文件不是当天爬取，则重新爬取并删除旧的文件
    :param html_fp:
    :param json_fp:
    :return:
    """
    today = datetime.today()
    p = Path(html_fp)
    # 文件过期则删除重爬
    if p.exists():
        df_mt = dateparser.parse(str(p.stat().st_mtime))
        y, m, d = df_mt.year, df_mt.month, df_mt.day
        is_not_overdue = all([y == today.year, m == today.month, d == today.day])
        if not is_not_overdue:
            p.unlink()
            if json_fp:
                jp = Path(json_fp)
                if p.exists():
                    jp.unlink()
    return 0


class ParseData:

    def __init__(self):
        pass

    @staticmethod
    def get_data_from_json(json_fp: Union[str, Path]) -> Union[dict, list]:
        """
        从指定的json文件中解析数据
        :param json_fp:str,文件路径
        :return:dict,
        """
        if Path(json_fp).exists():
            with open(json_fp, encoding='utf-8') as f:
                data = json.load(f)
            return data
        else:
            raise FileNotFoundError(f'File:{json_fp} not Found.')

    @staticmethod
    def get_data_from_yaml(yaml_fp: Union[str, Path]):
        """
        从指定的yaml文件中解析数据
        :param yaml_fp:文件路径
        :return: dict,
        """
        with open(yaml_fp) as f:
            data = yaml.load(f, Loader=yaml.FullLoader)
        return data


data_parser = ParseData()

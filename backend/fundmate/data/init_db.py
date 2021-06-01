#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/29 16:03
import json
from pathlib import Path
from typing import Union
import yaml

CURRENT_PATH = Path(__file__).resolve().parent
ALL_JSON_FP = Path(CURRENT_PATH, 'all.json')


class ParseData:

    def __init__(self):
        pass

    @staticmethod
    def get_data_from_json(json_fp: Union[str, Path]):
        """
        从指定的json文件中解析数据
        :param json_fp:str,文件路径
        :return:dict,
        """
        with open(json_fp, encoding='utf-8') as f:
            data = json.load(f)
        return data

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


pd = ParseData()


class NewDB:

    def fund_type(self):
        """
        :return: set,{'定开债券', 'QDII-指数', '混合-FOF', '固定收益', '股票型', '其他创新', '债券型', '混合型', 'QDII-ETF', '分级杠杆', 'ETF-场内', '货币型', '债券指数',
         '理财型', '股票指数', '股票-FOF', 'QDII', '联接基金'}
        """

        info = pd.get_data_from_json(ALL_JSON_FP)
        fund_lists = info.get('data')
        type_set = set()
        for fund in fund_lists:
            fcode = fund[0]
            fname = fund[2]
            ftype = fund[3]
            if ftype not in type_set:
                type_set.add(ftype)
        return type_set


if __name__ == '__main__':
    ndb = NewDB()
    print(ndb.fund_type())

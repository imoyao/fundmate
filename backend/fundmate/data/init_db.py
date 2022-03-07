#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/29 16:03
from pathlib import Path

from backend.fundmate.data.utils.base import data_parser

CURRENT_PATH = Path(__file__).resolve().parent
ALL_JSON_FP = Path(CURRENT_PATH, 'all.json')


class NewDB:

    def fund_type(self):
        """
        获取基金类型 :return: set,{'定开债券', 'QDII-指数', '混合-FOF', '固定收益', '股票型', '其他创新', '债券型', '混合型',0
         'QDII-ETF', '分级杠杆', 'ETF-场内', '货币型', '债券指数', '理财型', '股票指数', '股票-FOF', 'QDII', '联接基金'}
        """

        info = data_parser.get_data_from_json(ALL_JSON_FP)
        fund_lists = info.get('data')
        type_set = set()
        # 11736
        for fund in fund_lists:
            # f_code = fund[0]
            # f_name = fund[2]
            f_type = fund[3]
            if f_type not in type_set:
                type_set.add(f_type)
        return type_set


if __name__ == '__main__':
    ndb = NewDB()
    print(ndb.fund_type())

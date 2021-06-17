#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/30 11:03


class HowBuy:

    def company(self):
        """
        orgin: https://www.howbuy.com/fund/company/  
        api: https://www.howbuy.com/fund/company/ajax.htm
        """
        url = 'https://www.howbuy.com/fund/company/ajax.htm'
        item = {
            "clrq": "2004-11-08",  # 成立日期
            "jdjf": "8.3",  # 评分
            "jgdm": "80041198",  # 公司代码
            "jgjc": "天弘基金",  # 名称
            "jjdm": "001632",  # 代表基金
            "jjhb": 99.94917,  # 一年收益
            "jjjc": "天弘中证食品饮料指数C",  # 代表基金名称
            "jjjlsl": 32,  # 经理数量
            "jjsl": 166,  # 基金数量
            "jjzcjz": 1.43527906996264E12,  # 管理规模（亿元）
            "rydm": "30180540",  # 经理代码
            "ryxm": "姜晓丽"  # 经理姓名
        }
        return item.keys()


hb = HowBuy()

if __name__ == '__main__':
    print(hb.company())

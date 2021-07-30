#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[leytou/FundsDateViewer: 基金赎回费率计算工具](https://github.com/leytou/FundsDateViewer)
"""

from itertools import islice

from backend.fundmate.libs.redeem_fee import figure, fund_list, hold


def chunks(data, size=10000):
    it = iter(data)
    for i in range(0, len(data), size):
        yield {k: data[k] for k in islice(it, size)}


def main():
    hold_data = hold.get_hold_data_from_excel()
    print('hold_data:', hold_data)

    li = fund_list.get_fund_list()
    for item in chunks(hold_data, 9):
        print('9item=====', item)
        figure.draw(item, li)
    figure.show()


if __name__ == "__main__":
    main()

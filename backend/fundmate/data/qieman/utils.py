#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/12/18 22:37
import hashlib
import time


def get_x_sign(split_len: int = 32):
    """
    see also: [python/etfplan.py at master · leighjpeter/python](
    https://github.com/leighjpeter/python/blob/master/practice/etfplan.py) 前13位是一个时间戳，后32位则是通过时间戳加密形成的一个加密字符； :param
    split_len: :return:
    """
    cur_time = str(time.time()).replace('.', '')[:13]
    target = f'{float(cur_time) * 1.01}'
    target = target[0:13]
    sha256 = hashlib.sha256()
    sha256.update(target.encode('utf-8'))
    target_sha256 = sha256.hexdigest().upper()
    x_sign = f'{cur_time}{target_sha256[:split_len]}'
    return x_sign


if __name__ == '__main__':
    sign = get_x_sign()
    print(sign)

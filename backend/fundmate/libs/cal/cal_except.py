#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Administrator at 2021/1/24 22:19
"""
[8. 错误和异常 — Python 3.9.1 文档](https://docs.python.org/zh-cn/3/tutorial/errors.html)
"""


class CalError(Exception):
    def __init__(self, message):
        super().__init__(message)


class LenEqualError(CalError):
    def __init__(self, message="Length is not equal!"):
        super().__init__(message)
        self.msg = message

    def __str__(self):
        return self.msg


class ParseError(CalError):
    def __init__(self, message):
        super().__init__(message)
        self.msg = message

    def __str__(self):
        return self.msg

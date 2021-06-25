#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/6/7 15:49
"""
[8. 错误和异常 — Python 3.9.1 文档](https://docs.python.org/zh-cn/3/tutorial/errors.html)
"""


class FmException(Exception):

    def __init__(self, message):
        super().__init__(message)


class CalError(FmException):
    """
    计算错误的异常
    """
    pass


class LenEqualError(CalError):
    """
    长度不相等的异常
    """

    def __init__(self, message="Length is not equal!"):
        super().__init__(message)
        self.msg = message

    def __str__(self):
        return self.msg


class ParseError(CalError):
    """
    解析异常
    """

    def __init__(self, message):
        super().__init__(message)
        self.msg = message

    def __str__(self):
        return self.msg


class CrawlerException(FmException):
    """
    爬虫类的异常
    """
    pass

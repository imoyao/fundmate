#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/6/7 15:49
"""
[8. 错误和异常 — Python 3.9.1 文档](https://docs.python.org/zh-cn/3/tutorial/errors.html)
"""


class FmException(Exception):
    """所有错误Exception的父类
    """

    def __init__(self, message):
        super().__init__(message)


class CalError(FmException):
    """
    计算错误的异常
    """
    pass


class NotSupportError(FmException):
    """
    暂不支持处理
    """
    pass


class UniqueInstanceError(FmException):
    """
    该操作必须保证查询结果唯一性
    """
    pass


class UnexpectedArgsError(FmException):
    """
    参数设置错误
    """
    pass


class UnpackError(FmException):
    """
    数据解包出错
    """
    pass


class PasswordNotExistsError(FmException):
    """
    必须提供用户密码
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


class ArgsEmptyError(CalError):
    """
    计算参数不能为空的异常
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


class IsClosedDurationError(CalError):
    """
    封闭期基金数据无法解析
    """
    pass


class CrawlerException(FmException):
    """
    爬虫类的异常
    """
    pass


class EmptyError(CrawlerException):
    """
    查询数据端为空
    """
    pass


class NotSupportPlatError(CrawlerException):
    """
    目前未支持该平台
    """
    pass


class FundQueryError(FmException):
    """基金信息查询出错
    """
    pass


class ImproperlyConfigured(FmException):
    """
    SQLAlchemy-Utils is improperly configured; normally due to usage of
    a utility that depends on a missing library.
    """
    pass

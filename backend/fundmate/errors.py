#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/27 14:09
@file: errors.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 暴露给用户端的错误提示，注意和excepts进行区分
"""

from apiflask import HTTPError


class NotHundredPercentSumPortion(HTTPError):
    status_code = 400
    message = '组合比例必须合计为100%！'
    extra_data = {'error_code': 1000, 'docs': ''}


class PatchWithEmptyData(HTTPError):
    status_code = 400
    message = '更新时提交数据不能为空。'
    extra_data = {'error_code': 1001, 'docs': ''}


class NoLookupUser(HTTPError):
    status_code = 400
    message = '查找用户失败，请确认邮箱地址是否填写正确？'
    extra_data = {'error_code': 1002, 'docs': ''}


class ConfirmedFirst(HTTPError):
    status_code = 400
    message = '为确保本人注册，请查收邮件激活账号！'
    extra_data = {'error_code': 1003, 'docs': ''}

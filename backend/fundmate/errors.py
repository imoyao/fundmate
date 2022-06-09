#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2021/12/27 14:09
@file: errors.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 暴露给用户端的错误提示，注意和excepts进行区分
## 大类
正常：0000
未知错误：9999
用户输入错误：1000 开头
第三方依赖错误：2000 开头
爬虫服务错误：3000 开头
客户端错误：4000 开头
服务端错误：5000 开头
中间件（数据库）错误：6000 开头
数据冲突错误：7000 开头
...
## 派生类
继承自大类，如果不指定http状态码，则默认返回继承的类的http状态码，注意：服务端错误码不一定都是5xx，该系统错误是在项目的维度来区分的，和http中的服务端错误不一定相同。
"""

from enum import Enum, unique

from apiflask import HTTPError


@unique
class StatusCodeError(Enum):
    """状态码枚举类，@unique保证错误码唯一"""
    OK = (0000, '成功')
    UNKNOWN_ERR = (9999, '未知错误')
    USER_INPUT_ERR = (1000, '用户输入错误')
    THIRD_PART_ERR = (2000, '第三方依赖错误')
    CRAWLER_ERR = (3000, '爬虫服务错误')  # 一般不会报error，而是通过exception处理
    CLIENT_ERR = (4000, '客户端错误')
    SERVER_ERR = (5000, '服务端错误')
    MIDDLEWARE_ERR = (6000, '中间件错误')
    DATA_CONFLICT_ERR = (7000, '数据冲突错误')

    # 用户输入错误派生
    NOT_HUNDRED_PERCENT_SUM_PORTION_ERR = (1001, '组合比例必须合计为100%')
    PATCH_WITH_EMPTY_DATA_ERR = (1002, '更新时提交数据不能为空。')
    NO_LOOKUP_USER_ERR = (1003, '查找用户失败，请确认邮箱地址是否填写正确？')
    PROD_ALREADY_EXIST_ERR = (1004, '创建产品已存在，请使用查询页面获取该产品相关信息。')

    # 第三方依赖错误派生
    PRAETORIAN_ERROR = (2001, '组件`flask_praetorian` 发生错误。')
    MISSING_CLAIM_ERROR = (2002, '认证失败，请联系系统管理员。')
    EXPIRED_ACCESS_ERROR = (2003, 'Token 已过期，请重新认证。')
    EARLY_REFRESH_ERROR = (2004, '目前不需要刷新 Token')
    MISSING_TOKEN = (2005, "['header', 'cookie'] 中未找到 Token")
    INVALID_TOKEN_HEADER = (2006, '非法Token头')
    AUTHENTICATION_ERROR = (2007, '认证失败，请联系系统管理员。')

    # 爬虫服务错误
    THERMOMETER_ERR = (3001, '市场温度数据获取失败。')

    # 客户端错误派生
    CONFIRMED_FIRST_ERR = (4001, '为确保本人注册，请查收邮件激活账号！')
    NOT_EXCEPTED_FILE_ERR = (4002, '请确保上传文件格式正确！')
    NOT_EXCEPTED_PROD_ERR = (4003, '请确保上传文件中所有产品均支持导入！')
    NOT_SUPPORT_INVEST_TYPE_ERR = (4004, '请确保所有交易操作均支持导入')

    # 服务端错误派生
    CURRENT_USER_INFO_ERR = (5001, '获取用户信息出错，请联系系统管理员。')
    TRANSACTION_RECORD_ERR = (5002, '保存数据到系统出错（列名不匹配）！')

    # 数据冲突错误
    FORBIDDEN_DENY_ADMIN_ERR = (7001, '系统管理员不允许被禁用，以免系统自锁。')

    @property
    def status_code(self):
        """获取状态码"""
        return self.value[0]

    @property
    def message(self):
        """获取状态码信息"""
        return self.value[1]

    @property
    def msg(self):
        return self.message

    @property
    def code(self):
        return self.status_code


# 基础错误类


class BaseStatusOK(HTTPError):
    status_code = 200
    message = StatusCodeError.OK.msg
    extra_data = {'error_code': StatusCodeError.OK.code, 'docs': ''}


class BaseUnknownError(HTTPError):
    status_code = 500
    message = StatusCodeError.UNKNOWN_ERR.msg
    extra_data = {'error_code': StatusCodeError.UNKNOWN_ERR.code, 'docs': ''}


class BaseUserInputError(HTTPError):
    status_code = 400
    message = StatusCodeError.USER_INPUT_ERR.msg
    extra_data = {'error_code': StatusCodeError.USER_INPUT_ERR.code, 'docs': ''}


class BaseThirdPartError(HTTPError):
    status_code = 500
    message = StatusCodeError.THIRD_PART_ERR.msg
    extra_data = {'error_code': StatusCodeError.THIRD_PART_ERR.code, 'docs': ''}


class BaseCrawlerError(HTTPError):
    status_code = 500
    message = StatusCodeError.CRAWLER_ERR.msg
    extra_data = {'error_code': StatusCodeError.CRAWLER_ERR.code, 'docs': ''}


class BaseClientError(HTTPError):
    status_code = 400
    message = StatusCodeError.CLIENT_ERR.msg
    extra_data = {'error_code': StatusCodeError.CLIENT_ERR.code, 'docs': ''}


class BaseServerError(HTTPError):
    status_code = 500
    message = StatusCodeError.SERVER_ERR.msg
    extra_data = {'error_code': StatusCodeError.SERVER_ERR.code, 'docs': ''}


class BaseMiddleWareError(HTTPError):
    status_code = 500
    message = StatusCodeError.MIDDLEWARE_ERR.msg
    extra_data = {'error_code': StatusCodeError.MIDDLEWARE_ERR.code, 'docs': ''}


class BaseDataConflictError(HTTPError):
    status_code = 500
    message = StatusCodeError.DATA_CONFLICT_ERR.msg
    extra_data = {'error_code': StatusCodeError.DATA_CONFLICT_ERR.code, 'docs': ''}


# 派生类


class NotHundredPercentSumPortionError(BaseUserInputError):
    message = StatusCodeError.NOT_HUNDRED_PERCENT_SUM_PORTION_ERR.msg
    extra_data = {'error_code': StatusCodeError.NOT_HUNDRED_PERCENT_SUM_PORTION_ERR.code, 'docs': ''}


class PatchWithEmptyDataError(BaseUserInputError):
    message = StatusCodeError.PATCH_WITH_EMPTY_DATA_ERR.msg
    extra_data = {'error_code': StatusCodeError.PATCH_WITH_EMPTY_DATA_ERR.code, 'docs': ''}


class NoLookupUserError(BaseUserInputError):
    message = StatusCodeError.NO_LOOKUP_USER_ERR.msg
    extra_data = {'error_code': StatusCodeError.NO_LOOKUP_USER_ERR.code, 'docs': ''}


class ProdAlreadyExistError(BaseUserInputError):
    message = StatusCodeError.PROD_ALREADY_EXIST_ERR.msg
    extra_data = {'error_code': StatusCodeError.PROD_ALREADY_EXIST_ERR.code, 'docs': ''}


class ConfirmedFirstError(BaseClientError):
    message = StatusCodeError.CONFIRMED_FIRST_ERR.msg
    extra_data = {'error_code': StatusCodeError.CONFIRMED_FIRST_ERR.code, 'docs': ''}


class NotExceptedFileError(BaseClientError):
    message = StatusCodeError.NOT_EXCEPTED_FILE_ERR.msg
    extra_data = {'error_code': StatusCodeError.NOT_EXCEPTED_FILE_ERR.code, 'docs': ''}


class NotSupportProduct(BaseClientError):
    message = StatusCodeError.NOT_EXCEPTED_PROD_ERR.msg
    extra_data = {'error_code': StatusCodeError.NOT_EXCEPTED_PROD_ERR.code, 'docs': ''}


class NotSupportInvestType(BaseClientError):
    message = StatusCodeError.NOT_SUPPORT_INVEST_TYPE_ERR.msg
    extra_data = {'error_code': StatusCodeError.NOT_SUPPORT_INVEST_TYPE_ERR.code, 'docs': ''}


class AuthError(BaseThirdPartError):
    status_code = 401
    message = StatusCodeError.AUTHENTICATION_ERROR.msg
    extra_data = {'error_code': StatusCodeError.AUTHENTICATION_ERROR.code, 'docs': ''}


class ForbiddenDenyAdminError(BaseThirdPartError):
    status_code = 403
    message = StatusCodeError.FORBIDDEN_DENY_ADMIN_ERR.msg
    extra_data = {'error_code': StatusCodeError.FORBIDDEN_DENY_ADMIN_ERR.code, 'docs': ''}


class CurrentUserInfoError(BaseServerError):
    message = StatusCodeError.CURRENT_USER_INFO_ERR.msg
    extra_data = {'error_code': StatusCodeError.CURRENT_USER_INFO_ERR.code, 'docs': ''}


class TransactionRecordError(BaseServerError):
    message = StatusCodeError.TRANSACTION_RECORD_ERR.msg
    extra_data = {'error_code': StatusCodeError.TRANSACTION_RECORD_ERR.code, 'docs': ''}


class ThermometerError(BaseCrawlerError):
    message = StatusCodeError.THERMOMETER_ERR.msg
    extra_data = {'error_code': StatusCodeError.THERMOMETER_ERR.code, 'docs': ''}


class PraetorianError(BaseThirdPartError):
    message = StatusCodeError.PRAETORIAN_ERROR.msg
    extra_data = {'error_code': StatusCodeError.PRAETORIAN_ERROR.code, 'docs': ''}


class MissingToken(PraetorianError):
    message = StatusCodeError.MISSING_TOKEN.msg
    extra_data = {'error_code': StatusCodeError.MISSING_TOKEN.code, 'docs': ''}


class ExpiredAccessError(PraetorianError):
    message = StatusCodeError.EXPIRED_ACCESS_ERROR.msg
    extra_data = {'error_code': StatusCodeError.EXPIRED_ACCESS_ERROR.code, 'docs': ''}

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
中间件（如数据库）错误：6000 开头
数据冲突错误：7000 开头
...
## 派生类
继承自大类，如果不指定http状态码，则默认返回继承的类的http状态码，注意：服务端错误码不一定都是5xx，该系统错误是在项目的维度来区分的，和http中的服务端错误不一定相同。
ref: https://stackoverflow.com/questions/69005034
"""

from enum import Enum, unique

from apiflask import HTTPError


class ErrorMixin:
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


class ErrorMeta(type(Enum), type(ErrorMixin)):
    pass


@unique
class BaseOK(ErrorMixin, Enum, metaclass=ErrorMeta):
    """状态码枚举类，@unique保证错误码唯一"""
    OK = (0000, '成功')


@unique
class BaseError(ErrorMixin, Enum, metaclass=ErrorMeta):
    """状态码枚举类，@unique保证错误码唯一"""
    UNKNOWN_ERR = (9999, '未知错误')


@unique
class UserInputError(ErrorMixin, Enum, metaclass=ErrorMeta):
    """
    # 用户输入错误派生
    """
    USER_INPUT_ERR = (1000, '用户输入错误')
    NOT_HUNDRED_PERCENT_SUM_PORTION_ERR = (1001, '组合比例必须合计为100%')
    PATCH_WITH_EMPTY_DATA_ERR = (1002, '更新时提交数据不能为空。')
    NO_LOOKUP_USER_ERR = (1003, '查找用户失败，请确认邮箱地址是否填写正确？')
    PROD_ALREADY_EXIST_ERR = (1004, '创建产品已存在，请使用查询页面获取该产品相关信息。')
    # 像这种比较通用的错误提示信息，允许在代码中进行文案自定义
    FORBIDDEN_DELETE_ERR = (1005, '删除失败，请确认被删除对象存在。')
    FORBIDDEN_UPDATE_ERR = (1006, '更新失败，请确认更新对象存在。')
    LABEL_IS_NOT_EXIST_ERR = (1007, '更新失败，请确认标签是否存在。')


@unique
class ThirdPartError(ErrorMixin, Enum, metaclass=ErrorMeta):
    """
    第三方依赖错误派生
    """
    THIRD_PART_ERR = (2000, '第三方依赖错误')
    PRAETORIAN_ERROR = (2001, '组件`flask_praetorian` 发生错误。')
    MISSING_CLAIM_ERROR = (2002, '认证失败，请联系系统管理员。')
    EXPIRED_ACCESS_ERROR = (2003, 'Token 已过期，请重新认证。')
    EARLY_REFRESH_ERROR = (2004, '目前不需要刷新 Token')
    MISSING_TOKEN = (2005, "['header', 'cookie'] 中未找到 Token")
    INVALID_TOKEN_HEADER = (2006, '非法Token头')
    AUTHENTICATION_ERROR = (2007, '认证失败，请联系系统管理员。')


@unique
class CrawlerError(ErrorMixin, Enum, metaclass=ErrorMeta):
    """
    爬虫服务错误
    一般不会报error，而是通过exception处理
    """
    CRAWLER_ERR = (3000, '爬虫服务错误')
    THERMOMETER_ERR = (3001, '市场温度数据获取失败。')


@unique
class ClientError(ErrorMixin, Enum, metaclass=ErrorMeta):
    """
    客户端错误派生
    """
    CLIENT_ERR = (4000, '客户端错误')
    CONFIRMED_FIRST_ERR = (4001, '为确保本人注册，请查收邮件激活账号！')
    NOT_EXCEPTED_FILE_ERR = (4002, '请确保上传文件格式正确！')
    NOT_EXCEPTED_PROD_ERR = (4003, '请确保上传文件中所有产品均支持导入！')
    NOT_SUPPORT_INVEST_TYPE_ERR = (4004, '请确保所有交易操作均支持导入')
    FORBIDDEN_DENY_ADMIN_ERR = (4005, '系统管理员不允许被禁用')
    COLLECTION_ERR = (4006, '请确认添加自选实例存在')
    HAS_CREATED_ERR = (4007, '已存在，请勿重复创建！')


@unique
class ServerError(ErrorMixin, Enum, metaclass=ErrorMeta):
    """
    服务端错误派生
    """
    SERVER_ERR = (5000, '服务端错误')
    CURRENT_USER_INFO_ERR = (5001, '获取用户信息出错，请联系系统管理员。')
    TRANSACTION_RECORD_ERR = (5002, '保存数据到系统出错（列名不匹配）！')


@unique
class MiddlewareError(ErrorMixin, Enum, metaclass=ErrorMeta):
    """
    中间件错误
    """
    MIDDLEWARE_ERR = (6000, '中间件错误')


@unique
class LogicConflictError(ErrorMixin, Enum, metaclass=ErrorMeta):
    """
    数据冲突错误
    """
    LOGIC_CONFLICT_ERR = (7000, '逻辑冲突错误')


class BaseStatusOK(HTTPError):
    status_code = 200
    message = BaseOK.OK.msg
    extra_data = {'error_code': BaseOK.OK.code, 'docs': ''}


class HTTPClientError(HTTPError):
    status_code = 400
    message = BaseError.UNKNOWN_ERR.msg
    extra_data = {'error_code': BaseError.UNKNOWN_ERR.code, 'docs': ''}


#
class HTTPServerError(HTTPError):
    status_code = 500
    message = BaseError.UNKNOWN_ERR.msg
    extra_data = {'error_code': BaseError.UNKNOWN_ERR.code, 'docs': ''}

# class HTTPThirdPartError(HTTPError):
#     status_code = 500
#     message = ThirdPartError.THIRD_PART_ERR.msg
#     extra_data = {'error_code': ThirdPartError.THIRD_PART_ERR.code, 'docs': ''}
#
#
# class HTTPCrawlerError(HTTPError):
#     status_code = 500
#     message = CrawlerError.CRAWLER_ERR.msg
#     extra_data = {'error_code': CrawlerError.CRAWLER_ERR.code, 'docs': ''}
#
#
# class HTTPClientError(HTTPError):
#     status_code = 400
#     message = ClientError.CLIENT_ERR.msg
#     extra_data = {'error_code': ClientError.CLIENT_ERR.code, 'docs': ''}
#
#
# class HTTPServerError(HTTPError):
#     status_code = 500
#     message = ServerError.SERVER_ERR.msg
#     extra_data = {'error_code': ServerError.SERVER_ERR.code, 'docs': ''}
#
#
# class HTTPMiddleWareError(HTTPError):
#     status_code = 500
#     message = MiddlewareError.MIDDLEWARE_ERR.msg
#     extra_data = {'error_code': MiddlewareError.MIDDLEWARE_ERR.code, 'docs': ''}
#
#
# class HTTPLogicConflictError(HTTPError):
#     status_code = 500
#     message = LogicConflictError.LOGIC_CONFLICT_ERR.msg
#     extra_data = {'error_code': LogicConflictError.LOGIC_CONFLICT_ERR.code, 'docs': ''}
#
#
# class NotHundredPercentSumPortionError(HTTPUserInputError):
#     message = UserInputError.NOT_HUNDRED_PERCENT_SUM_PORTION_ERR.msg
#     extra_data = {'error_code': UserInputError.NOT_HUNDRED_PERCENT_SUM_PORTION_ERR.code, 'docs': ''}
#
#
# class PatchWithEmptyDataError(HTTPUserInputError):
#     message = UserInputError.PATCH_WITH_EMPTY_DATA_ERR.msg
#     extra_data = {'error_code': UserInputError.PATCH_WITH_EMPTY_DATA_ERR.code, 'docs': ''}
#
#
# class NoLookupUserError(HTTPUserInputError):
#     message = UserInputError.NO_LOOKUP_USER_ERR.msg
#     extra_data = {'error_code': UserInputError.NO_LOOKUP_USER_ERR.code, 'docs': ''}
#
#
# class ProdAlreadyExistError(HTTPUserInputError):
#     message = UserInputError.PROD_ALREADY_EXIST_ERR.msg
#     extra_data = {'error_code': UserInputError.PROD_ALREADY_EXIST_ERR.code, 'docs': ''}
#
#
# class ConfirmedFirstError(HTTPClientError):
#     message = ClientError.CONFIRMED_FIRST_ERR.msg
#     extra_data = {'error_code': ClientError.CONFIRMED_FIRST_ERR.code, 'docs': ''}
#
#
# class NotExceptedFileError(HTTPClientError):
#     message = ClientError.NOT_EXCEPTED_FILE_ERR.msg
#     extra_data = {'error_code': ClientError.NOT_EXCEPTED_FILE_ERR.code, 'docs': ''}
#
#
# class NotSupportProduct(HTTPClientError):
#     message = ClientError.NOT_EXCEPTED_PROD_ERR.msg
#     extra_data = {'error_code': ClientError.NOT_EXCEPTED_PROD_ERR.code, 'docs': ''}
#
#
# class NotSupportInvestType(HTTPClientError):
#     message = ClientError.NOT_SUPPORT_INVEST_TYPE_ERR.msg
#     extra_data = {'error_code': ClientError.NOT_SUPPORT_INVEST_TYPE_ERR.code, 'docs': ''}
#
#
# class AuthError(HTTPThirdPartError):
#     status_code = 401
#     message = ThirdPartError.AUTHENTICATION_ERROR.msg
#     extra_data = {'error_code': ThirdPartError.AUTHENTICATION_ERROR.code, 'docs': ''}
#
#
# class ForbiddenDenyAdminError(HTTPClientError):
#     status_code = 403
#     message = ClientError.FORBIDDEN_DENY_ADMIN_ERR.msg
#     extra_data = {'error_code': ClientError.FORBIDDEN_DENY_ADMIN_ERR.code, 'docs': ''}
#
#
# class CurrentUserInfoError(HTTPServerError):
#     message = ServerError.CURRENT_USER_INFO_ERR.msg
#     extra_data = {'error_code': ServerError.CURRENT_USER_INFO_ERR.code, 'docs': ''}
#
#
# class TransactionRecordError(HTTPServerError):
#     message = ServerError.TRANSACTION_RECORD_ERR.msg
#     extra_data = {'error_code': ServerError.TRANSACTION_RECORD_ERR.code, 'docs': ''}
#
#
# class ThermometerError(HTTPCrawlerError):
#     message = CrawlerError.THERMOMETER_ERR.msg
#     extra_data = {'error_code': CrawlerError.THERMOMETER_ERR.code, 'docs': ''}
#
#
# class PraetorianError(HTTPThirdPartError):
#     message = ThirdPartError.PRAETORIAN_ERROR.msg
#     extra_data = {'error_code': ThirdPartError.PRAETORIAN_ERROR.code, 'docs': ''}
#
#
# class MissingToken(PraetorianError):
#     message = ThirdPartError.MISSING_TOKEN.msg
#     extra_data = {'error_code': ThirdPartError.MISSING_TOKEN.code, 'docs': ''}
#
#
# class ExpiredAccessError(PraetorianError):
#     message = ThirdPartError.EXPIRED_ACCESS_ERROR.msg
#     extra_data = {'error_code': ThirdPartError.EXPIRED_ACCESS_ERROR.code, 'docs': ''}

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/1/26 13:51
@file: dk_enums.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 定义choices数据类型所需要的基础数据
"""
import enum
from types import DynamicClassAttribute

from backend.fundmate.libs.dataklasses import dataklass


@dataklass
class ChoiceTypeIntegerDk:
    """
    数据库中存的是数字
    保存时输入拼音
    显示时应为可读信息
    """
    value: int
    name: str
    label: str

    @property
    def display(self):
        return self.label


@dataklass
class ChoiceTypeDk:
    value: str
    label: str

    @property
    def display(self):
        return self.label


@enum.unique
class BaseTypeEnum(enum.Enum):

    def __str__(self):
        return f'Custom TypeEnum {self.value}'

    @DynamicClassAttribute
    def dk_name(self):
        """The name of the Enum member."""
        try:
            return self._value_.name
        except AttributeError:
            raise AttributeError('Please use `dk_value` while value is instance of `ChoiceTypeDk`.')

    @DynamicClassAttribute
    def dk_value(self):
        """The value of the Enum member."""
        return self._value_.value

    @DynamicClassAttribute
    def label(self):
        """The label of the Enum member."""
        return self._value_.label

    @DynamicClassAttribute
    def dk_display(self):
        """alias of label"""
        return self.label

    @DynamicClassAttribute
    def display(self):
        """alias of label"""
        return self.label

    def describe(self):
        # self is the member here
        return self.name, self.value

    @classmethod
    def values(cls):
        """
        >>> r.values()
        [ChoiceTypeIntegerDk(0, 'undefined', '未定义'),
         ChoiceTypeIntegerDk(1, 'plain', '灵活取用'),
         ChoiceTypeIntegerDk(2, 'low', '稳健增值'),
         ChoiceTypeIntegerDk(3, 'balance', '平衡增长'),
         ChoiceTypeIntegerDk(4, 'advance', '进阶成长'),
         ChoiceTypeIntegerDk(5, 'high', '积极进取')]

        :return:
        """
        return [member.value for member in cls]

    @classmethod
    def names(cls):
        """
        只有当是value是int时才可以调用该方法，注意和定义类的`input`区分
        Example:
        >>> r.names()
        ['undefined', 'plain', 'low', 'balance', 'advance', 'high']

        :return:
        """
        empty = ['__empty__'] if hasattr(cls, '__empty__') else []
        return empty + [member.name for member in cls]

    @classmethod
    def labels(cls):
        """
        Example:
        >>> r = RiskTypeEnum
        >>> r.labels()
        ['未定义', '灵活取用', '稳健增值', '平衡增长', '进阶成长', '积极进取']
        :return:
        """
        return [member.label for member in cls]

    @classmethod
    def choices(cls):
        """
        >>> r = RiskTypeEnum
        >>> r.choices()
        [(0, '未定义'), (1, '灵活取用'), (2, '稳健增值'), (3, '平衡增长'), (4, '进阶成长'), (5, '积极进取')]

        :return:
        """
        empty = [(None, cls.__empty__)] if hasattr(cls, '__empty__') else []
        return empty + [(member.dk_value, member.label) for member in cls]

    @classmethod
    def comment(cls) -> str:
        """
        返回 key 和 label 对应的字典（字符串类型）
        :return:
        """
        enum_explains = dict()
        for name, member in cls.__members__.items():
            key = member.dk_value
            enum_explains[key] = member.dk_display
        return str(enum_explains)

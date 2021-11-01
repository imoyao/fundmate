#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/9/26 10:27
"""
通过该部分代码对pytest有一个基础认识，测试代码
"""
import time

import pytest


# 定义fixture 函数
@pytest.fixture()
def before_func():
    print('Every func do this.')
    return 'hello'


# 直接调用


def test_bar(before_func):
    print('bar……')
    name = f'{before_func},Peter'
    assert name == 'hello,Peter'


# 通过usefixtures装饰器


@pytest.mark.usefixtures("before_func")
def test_1():
    print('in test_1()')


@pytest.mark.usefixtures("before_func")
def test_2():
    print('in test_2()')


# 类中的每个成员函数进行声明


class Test1:

    @pytest.mark.usefixtures("before_func")
    def test_3(self):
        print('test_1()')

    @pytest.mark.usefixtures("before_func")
    def test_4(self):
        print('test_2()')


# 类之前声明
@pytest.mark.usefixtures("before_func")
class Test2:

    def test_5(self):
        print('test_1()')

    def test_6(self):
        print('test_2()')


# 用autos调用fixture
@pytest.fixture(scope="module", autouse=True)
def mod_header(request):
    print('\n-----------------')
    print('MODULE      : %s' % request.module.__name__)
    print('-----------------')


@pytest.fixture(scope="function", autouse=True)
def func_header(request):
    print('\n-----------------')
    print('FUNCTION    : %s' % request.function.__name__)
    print('time        : %s' % time.asctime())
    print('-----------------')


def test_one():
    print('in test_one()')


def test_two():
    print('in test_two()')


# 带返回值
@pytest.fixture(params=[1, 2, 3])
def test_pass_data(request):
    return request.param


def test_not_2(test_pass_data):
    print('test_data: %s' % test_pass_data)
    assert test_pass_data != 2

---
title:关键字
---
# 一些涉及的关键字及用法

## yield 实现 teardown

用 `fixture` 实现 `teardown` 并不是一个独立的函数，而是用 `yield` 关键字来开启 `teardown` 操作。

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pytest


@pytest.fixture(scope="session")
def open():
    # 会话前置操作setup
    print("===开始执行测试用例===")
    yield
    # 会话后置操作teardown
    print("===测试用例执行完成===")


@pytest.fixture
def login(open):
    # 方法级别前置操作setup
    print("===登陆操作login===")
    name = "===账号==="
    pwd = "===密码==="
    # 返回变量
    yield name, pwd
    # 方法级别后置操作teardown
    print("===登录成功login===")


def test_case1(login):
    print("===测试用例1===")
    # 返回的是一个元组
    print(login)
    # 分别赋值给不同变量
    name, pwd = login
    print(name, pwd)
    assert "账号" in name
    assert "密码" in pwd


def test_case2(login):
    print("===测试用例2===")
    print(login)


if __name__ == '__main__':
    pytest.main(['test_demo.py', '-s'])

```

我们来查看一下执行结果：

```plain
============================= test session starts =============================
platform win32 -- Python 3.8.8, pytest-6.2.5, py-1.11.0, pluggy-1.0.0
rootdir: C:\Users\hzxy\PycharmProjects\pytest_api_demo, configfile: pytest.ini
plugins: allure-pytest-2.9.45
collected 2 items

test_demo.py 这里返回了一个token
===开始执行测试用例===
===登陆操作login===
===测试用例1===
('===账号===', '===密码===')
===账号=== ===密码===
.===登录成功login===
===登陆操作login===
===测试用例2===
('===账号===', '===密码===')
.===登录成功login===
===测试用例执行完成===


============================== 2 passed in 0.03s ==============================

```

**注意**：

* 如果 yield 前面的代码，即 setup 部分已经抛出异常，则不会执行 yield 后面的 teardown 内容。
* 如果测试用例抛出异常，yield 后面的 teardown 内容还是会正常执行。

## yield+with 的结合

yield 也可以配合 with 语句使用。

```python
import pytest
import smtplib

@pytest.fixture(scope="module")
def smtp_connection():
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=5) as smtp_connection:
        # 在 yield 后面添加smtp_connection，则类似 return，返回 smtp_connection信息
        yield smtp_connection

```

## addfinalizer 终结函数

除了 `yield` 可以实现 `teardown` ，在 `request-context` 对象中注册 `addfinalizer` 方法也可以实现终结函数。

在用法上，`addfinalizer` 跟 `yield` 是不同的，需要你去注册作为终结器使用的函数。例如：增加一个函数 `fin` ，并且注册成终结函数。

```python
import pytest


@pytest.fixture(scope="module")
def test_addfinalizer(request):
    # 前置操作setup
    print("===打开浏览器===")
    test = "test_addfinalizer"


    def fin():
        # 后置操作teardown
        print("===关闭浏览器===")

    request.addfinalizer(fin)
    # 返回前置操作的变量
    return test


def test_case(test_addfinalizer):
    print("===最新用例===", test_addfinalizer)
```

返回结果：

```plain
============================= test session starts =============================
platform win32 -- Python 3.8.8, pytest-6.2.5, py-1.11.0, pluggy-1.0.0
rootdir: C:\Users\hzxy\PycharmProjects\pytest_api_demo, configfile: pytest.ini
plugins: allure-pytest-2.9.45
collected 1 item

test_demo.py 这里返回了一个token
===打开浏览器===
===最新用例=== test_addfinalizer
.===关闭浏览器===


============================== 1 passed in 0.02s ==============================
```

### yield 与 addfinalizer 的区别

`addfinalizer 可以注册多个终结函数。`

```python
import pytest

@pytest.fixture()
def demo_addfinalizer(request):
    print("====setup====")

    def fin1():
        print("====teardown1====")

    def fin2():
        print("====teardown2====")

    def fin3():
        print("====teardown3====")

    # 注册demo_addfinalizer为终结函数
    request.addfinalizer(fin1)
    request.addfinalizer(fin2)
    request.addfinalizer(fin3)


def test_case1(demo_addfinalizer):
    print("====执行用例test_case1====")


def test_case2(demo_addfinalizer):
    print("====执行用例test_case2====")


def test_case3(demo_addfinalizer):
    print("====执行用例test_case3====")


if __name__ == '__main__':
    pytest.main(['test_demo.py', '-s'])
```

返回结果：

```plain
============================= test session starts =============================
platform win32 -- Python 3.8.8, pytest-6.2.5, py-1.11.0, pluggy-1.0.0
rootdir: C:\Users\hzxy\PycharmProjects\pytest_api_demo, configfile: pytest.ini
plugins: allure-pytest-2.9.45
collected 3 items

test_demo.py 这里返回了一个token
====setup====
====执行用例test_case1====
.====teardown3====
====teardown2====
====teardown1====
====setup====
====执行用例test_case2====
.====teardown3====
====teardown2====
====teardown1====
====setup====
====执行用例test_case3====
.====teardown3====
====teardown2====
====teardown1====


============================== 3 passed in 0.04s ==============================
```

## 参考链接

[pytest 零基础入门到精通（04）conftest 文件详解_七月的小尾巴的博客-CSDN 博客](https://blog.csdn.net/weixin_43865008/article/details/121532380)

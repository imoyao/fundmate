---
title: 测试你的代码 | 未经测试的代码是不完整的
---

## 引言

关于测试的重要性不言而喻：

1. 没有测试过的应用将会使得提高现有代码质量很困难；
2. 未经测试的应用难于改进现有的代码，因此其开发者会越改进越抓狂。 反之，经过自动测试的代码可以安全的改进，并且可以在测试过程中立即发现错误。 如果一个应用拥有自动化测试，那么我们就可以放心地修改并立刻知道所做修改是否有错误。
   [XML 之父：不对代码做测试就像“上完厕所不洗手”](https://mp.weixin.qq.com/s/AgI0JCRfyaFzqrTAde4C9w)

## 框架选择

有的 Flask 教程中使用 unittest 作为测试工具，我们选择 pytest 作为测试的工具，它易于学习，而且与前者相比，它需要的样板代码更少。

具体对比参阅：[Python 测试框架对比 - 简书](https://www.jianshu.com/p/b87ec158aad8)

> 总体来说，unittest 比较基础，二次开发方便，适合高手使用；pytest/nose 更加方便快捷，效率更高，适合小白及追求效率的公司；robot framework 由于有界面及美观的报告，易用性更好，灵活性及可定制性略差。

## 使用

网上有很多介绍 pytest 的文章，但是多为简单 demo，很少结合实际开发。本项目介绍力争结合实际项目中如何使用。

咳，出发！

### 结合 PyCharm

- 设置 PyCharm 默认测试类型

1. 打开 File > Settings > Tools > Python Integrated Tools > Testing > Default test runner
2. 修改下拉框，改为"pytest"
3. 右键单元测试文件，点击"run"，即可执行测试，在下方的"Run"窗口也有相应的测试结果

- 设置执行所有测试 右键"tests"文件夹，选择"Run"
  接下来就直接跑目录下所有的测试用例了，在下方的"Run"窗口可以看到测试信息。 如果报错找不到模块时，需要打开右上角的编辑启动项，先删除旧信息，否则会有缓存

## Postman 与 pytest

postman 用于前端开发人员对接口进行测试，借助于 mock 服务器特性，我们可以打破前后端之间相互掣肘的问题，让开发人员各自专注于自己的分内之事，从而减少开发团队发布的消耗时间。

## postman

此处参考 [Building Restful API with Flask, Postman & PyTest - Part 2 (Read Time: 10 Mins) - MaxOngZB](https://www.maxongzb.com/building-restful-api-with-flask-postman-and-pytest-part-2-read-time-10-mins/)

- Collection 用于存放我们的 API 请求。
- mocks 可以选择我们自己创建的 collection 作为 mock 的标志。对于后端还没有开发好的接口，可以直接编辑请求。
:::info 讨论
  [单测时要不要 mock 数据库？ - Jiajun 的编程随想](https://jiajunhuang.com/articles/2021_08_27-mock_db_or_not.md.html)
:::

## pytest

主要参考该系列文章：
[Flask Rest API - Zero to Yoda Series' Articles - DEV Community](https://dev.to/paurakhsharma/series/3672)

- conftest

共享作用域，一个工程下可以建多个`conftest.py`的文件，一般在工程根目录下设置的 conftest 文件起到全局作用。在不同子目录下也可以放`conftest.py`的文件，作用范围只能在该层级及以下目录生效。

### fixture

本章节主要参考出处：
1. [Pytest 高级进阶之 Fixture - 简书](https://www.jianshu.com/p/54b0f4016300)
2. [pytest 框架之 fixture 详细使用 - 辉辉辉辉 a - 博客园](https://www.cnblogs.com/huizaia/p/10331469.html)

> 我们可以把 fixture 看做是资源，在你的测试用例执行之前需要去配置这些资源，执行完后需要去释放资源。比如 module 类型的 fixture，适合于那些许多测试用例都只需要执行一次的操作。 fixture 还提供了参数化功能，根据配置和不同组件来选择不同的参数。 fixture 主要的目的是为了提供一种可靠和可重复性的手段去运行那些最基本的测试内容。比如在测试网站的功能时，每个测试用例都要登录和退出，利用 fixture 就可以只做一次，否则每个测试用例都要做这两步也是冗余。

- fixture 的作用

fixture 的功能主要包括以下三点：

1. 传入测试中的数据集
2. 配置测试前系统的初始状态
3. 为批量测试提供数据源

- fixture 的使用

我们使用`@pytest.fixture()` 装饰器声明一个`fixture`函数，该 fixture 函数命名不需要以 test 开头，跟测试用例区分开。
基于此有三种不同调用方式：

1. 在测试用例中直接传 fixture 的函数参数名称调用

```python
def test_bar(before_func):
    print('bar……')
    name = f'{before_func},Peter'
    assert name == 'hello,Peter'
```

2. 用 fixture 装饰器`@pytest.mark.usefixtures()`调用 fixture
    1. 每个函数前声明
    ```python
    import pytest

    @pytest.fixture()
    def before():
        print('before each test')

    @pytest.mark.usefixtures("before")
    def test_1():
        print('in test_1()')

    @pytest.mark.usefixtures("before")
    def test_2():
        print('in test_2()')
    ```
    2. 封装在类中
        1. 类中的每个成员方法前用函数进行声明
       ```python
       import pytest
    
       class Test1:
            @pytest.mark.usefixtures("before")
            def test_3(self):
                print('test_1()')
         
            @pytest.mark.usefixtures("before")
            def test_4(self):
                print('test_2()')
        ```
        2. 在类前声明
       ```python
       import pytest
       
       @pytest.mark.usefixtures("before_func")
       class Test2:
     
           def test_5(self):
               print('test_1()')
     
           def test_6(self):
               print('test_2()')
       ```
3. 用 autos 调用 fixture 
 fixture 装饰器有一个配置参数 autouse，默认值为 False.
 在默认状态下，可以使用上面的方式调用 fixture，当设置为 True 时，在一个 scope 内的所有测试用例都会自动调用这个 fixture. 注意上面的 scope 的参数用于控制 fixture 的作用范围，其传参可以为：

   - function：函数级，每个测试用例都运行，为默认值
   - class：类级，每个类的所有测试用例运行一次
   - module：模块级，每个模块的所有测试用例运行一次
   - session：session 级，每个 session 级别运行一次
   及控制范围由大到小是：`session > module > class > function`

   示例代码：
   ```python
   import pytest
   import time
   
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
   ```
   正所谓能力越大，责任越大。使用该功能时需要谨慎小心并控制测试用例的范围。 比如你的所有测试用例都需要连接同一个数据库，那可以设置为 module，这样只需要连接一次数据库，对于模块内的所有测试，这样可以极大地提高运行效率。
:::
- `usefixtures`与传`fixture`区别

如果 fixture 有返回值，那么 usefixture 就无法获取到返回值。

当 fixture 需要用到 return 出来的参数时，只能将参数名称直接当作参数传入，不需要用到 return 出来的参数时，两种方式都可以。
:::

- 带参数与返回值
上面的示例中我们都只是简单调用，同时我们可以选择让 fixture 返回我们需要的东西。如果你的 fixture 需要配置一些数据，读个文件，或者连接一个数据库，那么你可以让 fixture 返回这些数据或资源。
1. 带参数
```python
import pytest

@pytest.fixture(params=[1, 2, 3])
def pass_data(request):
    return request.param


def test_not_2(pass_data):
    print(f'test_data: {pass_data}')
    assert pass_data != 2
```
2. 带返回值
在`before_func`中我们已经实现。

如果想看 fixture 的执行过程，可以用 `--setup-show` 选项

### 多个参数一次测试

有的时候我们的代码里面会逻辑比较复杂，需要多个测试用例去验证，这个时候使用`pytest.mark.parametrize`可以实现批量传参；
1. argnames
单值使用`'single_args'`传递，多值可以使用逗号隔开的字符串，形如：`args,with,quota`，或者是内字符串列表或元祖；
```python
import pytest
@pytest.mark.parametrize(['suffix_str', 'replace_flag', 'expected'], [('100万', 'w', 1000000), ('7.0天', 'd', 7),('2.0年', 'n', 730)])
def test_foo():
    pass

@pytest.mark.parametrize('suffix_str,replace_flag,expected', [('100万', 'w', 1000000), ('7.0天', 'd', 7), ('2.0年', 'n', 730)])
def test_foo1():
    pass
# 
@pytest.mark.parametrize(['suffix_str', 'replace_flag', 'expected'], [('100万', 'w', 1000000), ('7.0天', 'd', 7), ('2.0年', 'n', 730)])
def test_foo2():
    pass
```
2. argvalues
多个值时使用元祖来传递每一组值。
TODO: 似乎目前无法不传默认值，参阅：[Error using parametrize with default arguments · Issue #3221 · pytest-dev/pytest](https://github.com/pytest-dev/pytest/issues/3221)
3. indirect
如果设置成 True，则把传进来的参数当函数执行，而不是一个参数

### 测试类

可以在`setup_class`中实现类的实例化过程，保证仅被实例化一次。

### TODO

1. 使用 flask-pytest 测试我们的 flask 应用
2. 区分配置文件`.env`，使用不同的数据库
3. 测试 RESTful 接口

## 原则

### 测试隔离（Test Isolation）

> A good test set is self-sufficient and creates all the data it needs.

测试隔离是测试中最重要的概念之一。 通常在写测试时，我们每次只测试一个业务逻辑。测试隔离的理念是你的测试不应以任何方式影响另一个测试。

假定您在一个测试中创建了一个用户，而在另一个测试中测试登录功能。 为了遵循测试隔离，您不能依赖于用户创建测试中创建的用户进行测试，但应在要测试登录功能的测试中创建新的用户。
为什么？你的登录测试可能在用户创建测试之前运行，这样就会导致前者失败。

此外，如果我们没有删除我们在上一个测试用例中创建的用户，当我们尝试再次运行测试，我们的测试就会失败，因为用户已经存在。

因此，我们应该始终从空白状态测试一个功能，并且为此最简单的方法是删除数据库中的所有集合。

::: tip TODO 基础数据是否可以不遵循此条，否则，可能跑数据需要很久。

可以参考：
1. [关于数据库单元测试 // foolbear 的冥想盆](https://jxy.me/2016/05/06/db-unit-test/)
2. [优雅的进行数据库相关的单元测试 - 小破屋 | SJH Blog](https://songjunhao.github.io/2020/05/04/%E4%BC%98%E9%9B%85%E7%9A%84%E8%BF%9B%E8%A1%8C%E6%95%B0%E6%8D%AE%E5%BA%93%E7%9B%B8%E5%85%B3%E7%9A%84%E5%8D%95%E5%85%83%E6%B5%8B%E8%AF%95/)
:::

### 创建目录结构
1. 切换工作目录
 ```shell
 cd fundmate/backend
 ```
2.复制目录结构到指定目录，不包含文件
```shell
find fundmate -type d|grep -v 'venv'|grep -v '__pypackages__'|grep -v '__pycache__'|grep -v 'tests'| sed 's/fundmate/mkdir -p tests/' | sh
# 查找目录                排除目录                                                                      # 替换字符                        # 执行命令
```
注意如果需要，可以替换目录
## 参考阅读

### 框架选择

- [三种最流行的 Python 测试框架，我该用哪一个？ - 测试不将就 | awesometest](https://slxiao.github.io/2019/06/03/py-test/)
- [pluralsight/intro-to-pytest: An introduction to PyTest with lots of simple, hackable examples](https://github.com/pluralsight/intro-to-pytest)

### 文档

- [pytest: helps you write better programs — pytest documentation](https://docs.pytest.org/en/6.2.x/index.html)
  - 中文文档: [pyTest 官方手册(Release 4.2)之蹩脚翻译(1)_crazyskady 的博客-CSDN 博客](https://blog.csdn.net/crazyskady/article/details/87393268)
  - 更加顺口：[luizyao/pytest-chinese-doc: pytest 官方文档的中文翻译，但不仅仅是单纯的翻译，也包含自己的理解和实践。](https://github.com/luizyao/pytest-chinese-doc)
  - 更加完整：[Pytest：帮助您编写更好的程序 — pytest documentation](https://www.osgeo.cn/pytest/index.html)

### 简单使用

- [gothinkster/flask-realworld-example-app: Exemplary real world JSON API built with Flask (Python)](https://github.com/gothinkster/flask-realworld-example-app)
- [人人都能看懂的 Pytest 简易上手指南！](https://mp.weixin.qq.com/s/Z_lohJ9sVBexofTBRSmlHQ)
  - 系列文章：[测试高级进阶技能系列 - Pytest - 随笔分类(第 2 页) - 小菠萝测试笔记 - 博客园](https://www.cnblogs.com/poloyy/category/1690628.html?page=2) ✨
- [Create A Python Test Automation Project Using Pytest | TestProject](https://blog.testproject.io/2019/07/16/python-test-automation-project-using-pytest/)
- [Effective Python Testing With Pytest – Real Python](https://realpython.com/pytest-python-testing/)
- [Testing Python Applications with Pytest - Semaphore Tutorial](https://semaphoreci.com/community/tutorials/testing-python-applications-with-pytest)
- [Flask Rest API -Part:6- Testing REST APIs - DEV Community](https://dev.to/paurakhsharma/flask-rest-api-part-6-testing-rest-apis-4lla)
- [End-To-End Tutorial For Pytest Fixtures With Examples](https://www.lambdatest.com/blog/end-to-end-tutorial-for-pytest-fixtures-with-examples/)
- [Building Restful API with Flask, Postman & PyTest - Part 3 (Read Time: 20 Mins) - MaxOngZB](https://www.maxongzb.com/building-restful-api-with-flask-postman-and-pytest-part-3-read-time-20-mins/)
- [Testing a Flask Application using pytest – Patrick's Software Blog](https://www.patricksoftwareblog.com/testing-a-flask-application-using-pytest/)

### 其他

- [pytest-dev/pytest-flask: A set of pytest fixtures to test Flask applications](https://github.com/pytest-dev/pytest-flask)
- [Python 测试框架之 pytest 详解_lovedingd 的博客-CSDN 博客_pytest](https://blog.csdn.net/lovedingd/article/details/98952868)
- [Pytest - 使用介绍 - 简书](https://www.jianshu.com/p/a754e3d47671)
- [测试 Flask 应用 — Flask 0.10.1 文档](http://docs.jinkan.org/docs/flask/testing.html)
- [自动化测试基础篇：Selenium unittest 简介](https://mp.weixin.qq.com/s/D_2fYADN4Ypc2PzfTYPo4Q)
- [有关单元测试的 5 个建议](https://mp.weixin.qq.com/s/kHqZrDJhsu4v8ZEQ7QJ3wQ)

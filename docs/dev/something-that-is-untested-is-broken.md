---
title: 测试你的代码 | 未经测试的代码是不完整的
---
## 引言
关于测试的重要性不言而喻：
1. 没有测试过的应用将会使得提高现有代码质量很困难；
2. 未经测试的应用难于改进现有的代码，因此其开发者会越改进越抓狂。 反之，经过自动测试的代码可以安全的改进，并且可以在测试过程中立即发现错误。
如果一个应用拥有自动化测试，那么我们就可以安全的修改然后立刻知道是否有错误。

## 框架选择
有的 Flask 教程中使用 unittest 作为测试工具，经过阅读他人文件之后，我们选择 pytest 作为测试的工具，且这与官方文档中给出的选择一脉相承。
参阅：
- [Python 测试框架之 pytest 详解_lovedingd 的博客-CSDN 博客_pytest](https://blog.csdn.net/lovedingd/article/details/98952868)
- [Pytest - 使用介绍 - 简书](https://www.jianshu.com/p/a754e3d47671)
- 中文文档 [pyTest 官方手册(Release 4.2)之蹩脚翻译(1)_crazyskady 的博客-CSDN 博客](https://blog.csdn.net/crazyskady/article/details/87393268)
## 现有问题

网上有很多介绍pytest的文章，但是多为简单demo，很少结合实际开发。本项目介绍力争结合实际项目中如何使用。

## 咳，出发

### TODO

1. 区分配置文件`.env`，使用不同的数据库

### 测试隔离（Test Isolation）

测试隔离是测试中最重要的概念之一。 通常在写测试时，我们每次只测试一个业务逻辑。测试隔离的理念是你的测试不应以任何方式影响另一个测试。

假定您在一个测试中创建了一个用户，而在另一个测试中测试登录功能。 为了遵循测试隔离，您不能依赖于用户创建测试中创建的用户进行测试，但应在要测试登录功能的测试中创建新的用户。 为什么？你的登录测试可能在用户创建测试之前运行，这样就会导致前者失败。

此外，如果我们没有删除我们在上一个测试用例中创建的用户，当我们尝试再次运行测试，我们的测试就会失败，因为用户已经存在。

因此，我们应该始终从空白状态测试一个功能，并且为此最简单的方法是删除数据库中的所有集合。

::: TODO
基础数据是否可以不遵循此条，否则，可能跑数据需要很久。
:::

### 结合PyCharm
设置PyCharm默认测试类型
打开 File > Settings > Tools > Python Integrated Tools > Testing > Default test runner
修改下拉框，改为"pytest"
右键单元测试文件，点击"run"，即可执行测试，在下方的"Run"窗口也有相应的测试结果
设置执行所有测试
右键"tests"文件夹，选择"Run"
接下来就直接跑目录下所有的测试用例了，在下方的"Run"窗口可以看到测试信息
如果报错找不到模块时，需要打开右上角的编辑启动项，先删除旧信息，否则会有缓存

## 参考阅读
- [Examples and customization tricks — pytest documentation](https://docs.pytest.org/en/6.2.x/example/index.html)
- [gothinkster/flask-realworld-example-app: Exemplary real world JSON API built with Flask (Python)](https://github.com/gothinkster/flask-realworld-example-app)
- [pluralsight/intro-to-pytest: An introduction to PyTest with lots of simple, hackable examples](https://github.com/pluralsight/intro-to-pytest)
- [Create A Python Test Automation Project Using Pytest | TestProject](https://blog.testproject.io/2019/07/16/python-test-automation-project-using-pytest/)
- [Effective Python Testing With Pytest – Real Python](https://realpython.com/pytest-python-testing/)
- [Testing Python Applications with Pytest - Semaphore Tutorial](https://semaphoreci.com/community/tutorials/testing-python-applications-with-pytest)
- [Flask Rest API -Part:6- Testing REST APIs - DEV Community](https://dev.to/paurakhsharma/flask-rest-api-part-6-testing-rest-apis-4lla)
- [End-To-End Tutorial For Pytest Fixtures With Examples](https://www.lambdatest.com/blog/end-to-end-tutorial-for-pytest-fixtures-with-examples/)
- [三种最流行的 Python 测试框架，我该用哪一个？ - 测试不将就 | awesometest](https://slxiao.github.io/2019/06/03/py-test/)
- [测试 Flask 应用 — Flask 0.10.1 文档](http://docs.jinkan.org/docs/flask/testing.html)
- [Building Restful API with Flask, Postman & PyTest - Part 3 (Read Time: 20 Mins) - MaxOngZB](https://www.maxongzb.com/building-restful-api-with-flask-postman-and-pytest-part-3-read-time-20-mins/)
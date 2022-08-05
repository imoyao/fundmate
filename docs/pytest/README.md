---
title: 单元测试
---
看了一下，一篇文章不足以了解所有关于pytest的全貌，所以需要开一个章节来完整学习。

Pytest和Unittest测试框架的区别？
-----------------------

> 如何区分这两者，很简单unittest作为官方的测试框架，在测试方面更加基础，并且可以再次基础上进行二次开发，同时在用法上格式会更加复杂；而pytest框架作为第三方框架，方便的地方就在于使用更加灵活，并且能够对原有unittest风格的测试用例有很好的兼容性，同时在扩展上更加丰富，可通过扩展的插件增加使用的场景，比如一些并发测试等；

Pytest 安装
---------

pip安装：

    pip install pytest


测试安装成功：

    pytest --help

    py.test --help


检查安装版本：

    pytest --version


Pytest 示例
---------

Pytest编写规则:

*   测试文件以test\_开头（以\_test为结尾）
*   测试的类以Test开头；
*   测试的方法以test\_开头
*   断言使用基本的assert

test\_example.py

    def count_num(a: list) -> int:
        return len(a)


    def test_count():
        assert count_num([1, 2, 3]) != 3


执行测试：

    pytest test_example.py


执行结果：

    C:\Users\libuliduobuqiuqiu\Desktop\GitProjects\PythonDemo\pytest>pytest test_example.py -v
    ================================================================= test session starts =================================================================
    platform win32 -- Python 3.6.8, pytest-6.2.5, py-1.10.0, pluggy-1.0.0 -- d:\coding\python3.6\python.exe
    cachedir: .pytest_cache
    rootdir: C:\Users\libuliduobuqiuqiu\Desktop\GitProjects\PythonDemo\pytest
    plugins: Faker-8.11.0
    collected 1 item

    test_example.py::test_count FAILED                                                                                                               [100%]

    ====================================================================== FAILURES =======================================================================
    _____________________________________________________________________ test_count ______________________________________________________________________

        def test_count():
    >       assert count_num([1, 2, 3]) != 3
    E       assert 3 != 3
    E        +  where 3 = count_num([1, 2, 3])

    test_example.py:11: AssertionError
    =============================================================== short test summary info ===============================================================
    FAILED test_example.py::test_count - assert 3 != 3
    ================================================================== 1 failed in 0.16s ==================================================================


备注：

*   .代表测试通过，F代表测试失败；
*   \-v显示详细的测试信息， -h显示pytest命令详细的帮助信息；


## 资料
1. [Pytest和Allure测试框架-超详细版+实战_测试之道.的博客-CSDN博客_allure pytest](https://blog.csdn.net/qq_42610167/article/details/101204066)
2. [pytest和allure测试框架教程及应用【共14课时】_自动化测试课程-51CTO学堂](https://edu.51cto.com/course/18703.html)
3. [Pytest 自动化测试框架 - 掘金](https://juejin.cn/post/7013949685992259591)

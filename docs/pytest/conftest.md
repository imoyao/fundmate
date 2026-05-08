---
title:全局配置（conftest)
---

# 什么是conftest.py

可以理解成一个专门存放fixture的配置文件

实际开发场景
------

多个测试用例文件（test\_\*.py）的所有用例都需要**用登录功能来作为前置操作**，那就不能把登录功能写到某个用例文件中去了

如何解决上述场景问题？
-----------

conftest.py的出现，就是为了解决上述问题，单独管理一些全局的fixture

conftest.py配置fixture注意事项
------------------------

*   pytest会默认读取conftest.py里面的所有fixture
*   conftest.py 文件名称是固定的，不能改动
*   conftest.py只对同一个package下的所有测试用例生效
*   不同目录可以有自己的conftest.py，一个项目中可以有多个conftest.py
*   测试用例文件中不需要手动import conftest.py，pytest会自动查找

## 参考文档
1. [Pytest系列(2-3)-conftest详解 - 我是小菜鸡丫丫 - 博客园](https://www.cnblogs.com/kxtomato/p/16600613.html)

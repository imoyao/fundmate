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

## 参考阅读

- [三种最流行的 Python 测试框架，我该用哪一个？ - 测试不将就 | awesometest](https://slxiao.github.io/2019/06/03/py-test/)
- [测试 Flask 应用 — Flask 0.10.1 文档](http://docs.jinkan.org/docs/flask/testing.html)

---
title: 项目中代码规范问题
permalink: /dev/code-style
---
## 规范
我们以[PEP8](https://wiki.masantu.com/peps/pep-0008/)作为项目中的指导规范，为了饯行上述准则，我们引入以下工具帮助我们实践。

## 工具

### flake8
我们使用 flake8 进行 pep8 规范检查，具体安装参阅：[pycharm-guide/c08_15.md at master · imoyao/pycharm-guide](https://github.com/imoyao/pycharm-guide/blob/master/source/c08/c08_15.md)
```buildoutcfg
[flake8]
ignore = D401,D202,E226,E302,E41
max-line-length = 120
exclude = migrations/*,.git,__pycache__,old,build,dist
max-complexity = 10
```
[Pycharm 配置使用flake8进行语法检测_张聪的博客-CSDN博客](https://blog.csdn.net/crazy_zhangcong/article/details/87860276)

### isort
使用 isort 来解决自动导入的问题。下面一个我个人使用的配置，后期可能继续对比修改配置
```buildoutcfg
[isort]
multi_line_output = 3
include_trailing_comma = True
force_grid_wrap = 0
use_parentheses = True
balanced_wrapping = True
ensure_newline_before_comments = True
line_length = 79
known_flask = flask,flask_wtf,wtforms,flask_login,flask_bcrypt,flask_caching,flask_migrate,flask_sqlalchemy,flask_static_digest
known_test = pytest,webtest,factory
sections = FUTURE,STDLIB,FLASK,TEST,FIRSTPARTY,THIRDPARTY,LOCALFOLDER
```
`include_trailing_comma = True`的说明：

> 如果列表，元组或 python 字典的字面值分布在多行中，则更容易添加更多元素，因为不必记住在上一行中添加逗号。这些行也可以重新排序，而不会产生语法错误。

[为什么 Python 在列表和元组的末尾允许使用逗号？ - 红皮橘子 - 博客园](https://www.cnblogs.com/yuanrenxue/p/10691184.html)
此外处理预提交时的配置中增加：
[Pre Commit - isort](https://pycqa.github.io/isort/docs/configuration/pre-commit.html)

### yapf
一种自动修复 pep8 错误的工具
```buildoutcfg
[yapf]
based_on_style = pep8
spaces_before_comment = 2
split_before_logical_operator = true
BLANK_LINE_BEFORE_NESTED_CLASS_OR_DEF = true
COLUMN_LIMIT = 79
```
配置方案参考此处：[How do I install yapf in pycharm · Issue #631 · google/yapf](https://github.com/google/yapf/issues/631)

### mypy

[Applying mypy to real world projects](http://calpaterson.com/mypy-hints.html)

## 相关阅读

[我为什么不喜欢 black - 小明明 s à domicile](https://www.dongwm.com/post/why-i-dont-like-black/)
[How I use black, flake8 and isort to format Python2 code](https://thecesrom.dev/2021/03/06/how-i-use-black-flake8-and-isort-to-format-python2-code/)

配置可参考（TODO）：
[flask/setup.cfg at master · pallets/flask](https://github.com/pallets/flask/blob/master/setup.cfg)
[dkistdc / logging_config / setup.cfg — Bitbucket](https://bitbucket.org/dkistdc/logging_config/src/master/setup.cfg)
延伸到 setup.py 的写法
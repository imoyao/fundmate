---
title: 项目中代码规范问题
---
## 规范
我们以[PEP8](https://wiki.masantu.com/peps/pep-0008/)作为项目中的指导规范，为了饯行上述准则，我们引入以下工具帮助我们实践。

## 工具

### flake8
我们使用flake8进行pep8规范检查，具体安装参阅：[pycharm-guide/c08_15.md at master · imoyao/pycharm-guide](https://github.com/imoyao/pycharm-guide/blob/master/source/c08/c08_15.md)
```buildoutcfg
[flake8]
ignore = D401,D202,E226,E302,E41
max-line-length = 120
exclude = migrations/*,.git,__pycache__,old,build,dist
max-complexity = 10
```
### isort
使用isort来解决自动导入的问题。下面一个我个人使用的配置，后期可能继续对比修改配置
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

> 如果列表，元组或python字典的字面值分布在多行中，则更容易添加更多元素，因为不必记住在上一行中添加逗号。这些行也可以重新排序，而不会产生语法错误。

[为什么Python在列表和元组的末尾允许使用逗号？ - 红皮橘子 - 博客园](https://www.cnblogs.com/yuanrenxue/p/10691184.html)

### yapf
一种自动修复pep8错误的工具
```buildoutcfg
[yapf]
based_on_style = pep8
spaces_before_comment = 2
split_before_logical_operator = true
BLANK_LINE_BEFORE_NESTED_CLASS_OR_DEF = true
COLUMN_LIMIT = 79
```

## 相关阅读

[我为什么不喜欢 black - 小明明 s à domicile](https://www.dongwm.com/post/why-i-dont-like-black/)

配置可参考（TODO）：
[flask/setup.cfg at master · pallets/flask](https://github.com/pallets/flask/blob/master/setup.cfg)
[dkistdc / logging_config / setup.cfg — Bitbucket](https://bitbucket.org/dkistdc/logging_config/src/master/setup.cfg)
延伸到setup.py的写法
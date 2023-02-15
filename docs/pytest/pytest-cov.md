---
title:测试覆盖率(pytest-cov)
---
在测试测试用例的时候，需要对测试代码的覆盖率进行统计，我们使用`pytest-cov`实现此项功能。点击[pytest-cov ](https://pypi.org/project/pytest-cov/)了解。

## 用到的相关命令
比如要统计项目下user模块的代码，我们可以在项目根目录使用下面的命令
```python
pytest --cov=fundmate tests/user --cov-report=html
```
其中--cov后面跟测试的目录，后面可以指向测试脚本所在的目录，最后指定生成报告的格式。

## TODO

高级用法

## 注意事项
1. 会在根目录下生成`htmlcov`目录，需要在gitignore忽略；

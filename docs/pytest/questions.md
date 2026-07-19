---
title:问题记录
---

## pytest+click

1. 如何测试`click`包装的命令行？

   参阅[Testing Click Applications — Click Documentation (8.1.x)](https://click.palletsprojects.com/en/8.1.x/testing/)，需要使用`from click.testing import CliRunner`导入相应的包，然后如下调用：
   ```python
   runner = CliRunner()
   result = runner.invoke(function_name, [])
   ```
   对于 option 传参，可以显式传入参数到后面的列表中，也可以不传（此时即为 False）

2. 对于需要 confirm 传参的情况，如何传递`yes`参数给函数？

   参阅:
   1. [python - How do I pass input to click.confirm without running CLIrunner.invoke() - Stack Overflow](https://stackoverflow.com/questions/60217384/how-do-i-pass-input-to-click-confirm-without-running-clirunner-invoke)
   2. [click/test_utils.py at main · pallets/click](https://github.com/pallets/click/blob/main/tests/test_utils.py)
   ```python
   runner = CliRunner()
   result = runner.invoke(init_db, ['--drop'], input='n')       # input='y' 为确认
   ```
## `print`不生效

有的时候难免使用`print`大法调试，但是发现不会打印信息，这是因为 pytest 默认会捕捉各种输出，除非测试用例失败否则都过滤掉了，通过`-s`可以关闭捕捉(等于--capture=no)。需要执行`pytest -s your_test_script.py`

## 固件`request`是什么

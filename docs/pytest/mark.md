---
title:标记(mark)
---
## 标记(mark)
> 默认情况下，pytest 会在当前目录下寻找以 test\_为开头（以\_test 结尾）的测试文件，并且执行文件内所有以 test\_为开头（以\_test 为结尾）的所有函数和方法；

1. 指定运行测试用例，可以通过::显示标记（文件名::类名::方法名）（文件名::函数名）
    ```plain
    pytest test_example3.py::test_odd
    ```
2. 指定一些测试用例测试运行，可以使用-k 模糊匹配
    ```plain
    pytest -k example
    ```

3. 通过 pytest.mark.skip()或者 pytest.makr.skipif()条件表达式，跳过指定的测试用例

4. 通过 pytest.raises()捕获测试用例可能抛出的异常

5. 预先知道测试用例会失败，但是不想跳过，需要显示提示信息，使用 pytest.mark.xfail()

6. 对测试用例进行多组数据测试，每组参数都能够独立执行一次（可以避免测试用例内部执行单组数据测试不通过后停止测试）

使用 @pytest.mark.xxx 标记测试用例：

1.  可以标记测试方法、测试类，标记名可以自定义，最好起有意义的名字；
2.  同一测试类/方法可同时拥有多个标记；

    # test_login_logout.py import pytest  @pytest.mark.loginclass TestLogin:    """登陆功能测试类"""     @pytest.mark.smoke    @pytest.mark.success    def test_login_sucess(self):        """登陆成功"""         # 实现登陆逻辑        pass     @pytest.mark.failed    def test_login_failed(self):        """登陆失败"""         # 实现登陆逻辑        pass  @pytest.mark.logoutclass TestLogout:    """登出功能测试类"""     @pytest.mark.smoke    @pytest.mark.success    def test_logout_sucess(self):        """登出成功"""         # 实现登出功能        pass     @pytest.mark.failed    def test_logout_failed(self):        """登出失败"""         # 实现登出功能        pass

## 运行标记的用例：
1.  使用 -m 参数运行标记的测试用例；
2.  -m 参数支持 and、or 、not 等表达式；

    # 运行登陆功能的用例pytest.main(['-m login'])# 运行登出功能的用例pytest.main(['-m logout'])# 运行功能成功的用例pytest.main(['-m success'])# 运行功能失败的用例pytest.main(['-m failed'])# 运行登陆功能但是不运行登陆失败的测试用例pytest.main(['-m login and not failed'])# 运行登出功能但是不运行登出成功的测试用例pytest.main(['-m logout and not success'])# 运行登陆和登出的用例pytest.main(['-m login or logout'])

## 注册、管理 mark 标记：

当使用 -m 参数执行 mark 标记的用例时，pytest 会发出告警信息 “**PytestUnknownMarkWarning: Unknown pytest.mark.login - is this a typo? ”，**告诉你这是一个 pytest 未知的一个标记！为了消除告警，我们需要在 pytest 的配置文件中注册 mark 标记！

### 注册 mark 标记：

1.  首先在项目根目录创建一个文件 pytest.ini ，这个是 pytest 的配置文件；
2.  然后在 pytest.ini 文件的 markers 中写入你的 mark 标记， 冒号 “:” 前面是标记名称，后面是 mark 标记的说明，可以是空字符串；
3.  **注意：pytest.ini 文件中只能使用纯英文字符，绝对不能使用中文的字符（尤其是冒号和空格）！**

    # pytest.ini [pytest]markers =     login   : 'marks tests as login'    logout  : 'marks tests as logout'    success : 'marks tests as success'    failed  : 'marks tests as failed'

### 规范使用 mark 标记：

注册完 mark 标记之后 pytest 便不会再告警，但是有时手残容易写错 mark 名，导致 pytest 找不到用例，一时想不开很难debug，尤其是团队协作时很容易出现类似问题，所以我们需要 “addopts = --strict” 参数来严格规范 mark 标记的使用！

1. 在 pytest.ini 文件中添加参数 “addopts = --strict”；
2. 注意要另起一行，不要在 markers 中添加；
3. 添加该参数后，当使用未注册的 mark 标记时，pytest会直接报错：“ 'xxx' not found in \`markers\` configuration option ”，不执行测试任务；
4. **注意：pytest.ini 配置文件不支持注释，不支持注释，不支持注释...**
```ini
# pytest.ini

[pytest]
markers =
    login   : 'marks tests as login'
    logout  : 'marks tests as logout'
    success : 'marks tests as success'
    failed  : 'marks tests as failed'

addopts = --strict
```

## 总结
pytest 提供了一些拿来即用的标识：

- skip ：无条件跳过测试
- skipif：表达式判定为真则跳过测试
- xfail：期望测试失败，如果确实失败了，整轮测试的结果仍会是通过
- parametrize（注意拼写）：创建多个不同值的测试变量当参数。后面会提到
可以通过 `pytest --markers`查看完整的 pytest 标识列表

## 参考链接

[【pytest】使用 mark 标记及运行测试用例，注册、管理 mark 标记_waitan2018的博客-CSDN博客](https://blog.csdn.net/waitan2018/article/details/104022709)

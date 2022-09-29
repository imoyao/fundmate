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

```python
    import pytest

    test_flag = False

    @pytest.mark.skip()
    def test_odd():
        num = random.randint(0, 100)
        assert num % 2 == 1


    @pytest.mark.skipif(test_flag is False, reason="test_flag is False")
    def test_even():
        num = random.randint(0, 1000)
        assert num % 2 == 0
```

4. 通过 pytest.raises()捕获测试用例可能抛出的异常

```python
    def test_zero():
        num = 0
        with pytest.raises(ZeroDivisionError) as e:
            num = 1/0
        exc_msg = e.value.args[0]
        print(exc_msg)
        assert num == 0
```

5. 预先知道测试用例会失败，但是不想跳过，需要显示提示信息，使用 pytest.mark.xfail()

    ```python
    @pytest.mark.xfail()
    def test_sum():
        random_list = [random.randint(0, 100)  for x in range(10)]
        num = sum(random_list)
        assert num < 20
    ```

6. 对测试用例进行多组数据测试，每组参数都能够独立执行一次（可以避免测试用例内部执行单组数据测试不通过后停止测试）

    ```python
    @pytest.mark.parametrize('num,num2', [(1,2),(3,4)])
    def test_many_odd(num: int, num2: int):
        assert num % 2 == 1
        assert num2 % 2 == 0
    ```

进行测试的时候，你仍可以用 pytest 命令在默认模式下运行。如果想只跑需要访问数据库的测试，可以用 `pytest -m database_access`。要运行除请求访问数据库之外的所有测试，可以用 `pytest -m "not database_access"`。你甚至可以用 `autouse` fixture 限制那些标着 `database_access` 的测试对数据库的访问。

pytest 提供了一些拿来即用的标识：

- skip ：无条件跳过测试
- skipif：表达式判定为真则跳过测试
- xfail：期望测试失败，如果确实失败了，整轮测试的结果仍会是通过
- parametrize（注意拼写）：创建多个不同值的测试变量当参数。后面会提到
可以通过 `pytest --markers`查看完整的 pytest 标识列表

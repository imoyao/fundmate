---
title:参数化(parametrize)
---
## 参数化
> 前面简单的提到过了@pytest.mark.parametrize 通过参数化测试，而关于固件传入参数时则需要通过 pytest 框架中内置的固件 request，并且通过 request.param 获取参数

```python
    import pytest


    @pytest.fixture(params=[
        ('redis', '6379'),
        ('elasticsearch', '9200')
    ])
    def param(request):
        return request.param


    @pytest.fixture(autouse=True)
    def db(param):
        print('\nSucceed to connect %s:%s' % param)

        yield

        print('\nSucceed to close %s:%s' % param)


    def test_api():
        assert 1 == 1

```
执行结果：
```plain
    ============================= test session starts =============================
    platform win32 -- Python 3.6.8, pytest-6.2.5, py-1.10.0, pluggy-1.0.0 -- D:\Coding\Python3.6\python.exe
    cachedir: .pytest_cache
    rootdir: C:\Users\libuliduobuqiuqiu\Desktop\GitProjects\PythonDemo\pytest
    plugins: Faker-8.11.0
    collecting ... collected 2 items

    test_example.py::test_api[param0]
    Succeed to connect redis:6379
    PASSED                                 [ 50%]
    Succeed to close redis:6379

    test_example.py::test_api[param1]
    Succeed to connect elasticsearch:9200
    PASSED                                 [100%]
    Succeed to close elasticsearch:9200


    ============================== 2 passed in 0.07s ==============================
```


> 这里模拟连接 redis 和 elasticsearch，加载固件自动执行连接然后执行测试函数再断开连接。

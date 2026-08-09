---
title:固件（Fixture)
---
## 固件（Fixture)
>
> 固件就是一些预处理的函数，pytest 会在执行测试函数前（或者执行后）加载运行这些固件，常见的应用场景就有数据库的连接和关闭（设备连接和关闭）

简单使用

```python
    import pytest


    @pytest.fixture()
    def postcode():
        return "hello"


    def test_count(postcode):
        assert postcode == "hello"
```

> 按照官方的解释就是当运行测试函数，会首先检测运行函数的参数，搜索与参数同名的 fixture，一旦 pytest 找到，就会运行这些固件，获取这些固件的返回值（如果有），并将这些返回值作为参数传递给测试函数；

### 预处理和后处理

接下来进一步验证关于官方的说法：

```python
import pytest


@pytest.fixture()
def connect_db():
    print("Connect Database in .......")
    yield
    print("Close Database out .......")


def read_database(key: str):
    p_info = {
        "name": "zhangsan",
        "address": "China Guangzhou",
        "age": 99
    }
    return p_info[key]


def test_count(connect_db):
    assert read_database("name") == "zhangsan"

```

执行测试函数结果：

```plain
    ============================= test session starts =============================
    platform win32 -- Python 3.6.8, pytest-6.2.5, py-1.10.0, pluggy-1.0.0 -- D:\Coding\Python3.6\python.exe
    cachedir: .pytest_cache
    rootdir: C:\Users\libuliduobuqiuqiu\Desktop\GitProjects\PythonDemo\pytest
    plugins: Faker-8.11.0
    collecting ... collected 1 item

    test_example.py::test_count Connect Database in .......
    PASSED                                       [100%]Close Database out .......


    ============================== 1 passed in 0.07s ==============================

```

备注：

* 首先从结果上看验证了官方的解释，pytest 执行测试函数前会寻找同名的固件加载运行；
* connect\_db 固件中有 yield，这里 pytest 默认会判断 yield 关键词之前的代码属于预处理，会在测试前执行，yield 之后的代码则是属于后处理，将在测试后执行；

### 作用域

> 从前面大致了解了固件的作用，抽离出一些重复的工作方便复用，同时 pytest 框架中为了更加精细化控制固件，会使用作用域来进行指定固件的使用范围，（比如在这一模块中的测试函数执行一次即可，不需要模块中的函数重复执行）更加具体的例子就是数据库的连接，这一连接的操作可能是耗时的，我只需要在这一模块的测试函数运行一次即可，不需要每次都运行。

而定义固件是，一般通过 scop 参数来声明作用，常用的有：

* function: 函数级，每个测试函数都会执行一次固件；
* class: 类级别，每个测试类执行一次，所有方法都可以使用；
* module: 模块级，每个模块执行一次，模块内函数和方法都可使用；
* session: 会话级，一次测试只执行一次，所有被找到的函数和方法都可用。

```python
    import pytest

    @pytest.fixture(scope="function")
    def func_scope():
        print("func_scope")


    @pytest.fixture(scope="module")
    def mod_scope():
        print("mod_scope")


    @pytest.fixture(scope="session")
    def sess_scope():
        print("session_scope")


    def test_scope(sess_scope, mod_scope, func_scope):
        pass


    def test_scope2(sess_scope, mod_scope, func_scope):
        pass
```

执行结果：

```plain
    ============================= test session starts =============================
    platform win32 -- Python 3.6.8, pytest-6.2.5, py-1.10.0, pluggy-1.0.0 -- D:\Coding\Python3.6\python.exe
    cachedir: .pytest_cache
    rootdir: C:\Users\libuliduobuqiuqiu\Desktop\GitProjects\PythonDemo\pytest
    plugins: Faker-8.11.0
    collecting ... collected 2 items

    test_example2.py::test_scope session_scope
    mod_scope
    func_scope
    PASSED                                      [ 50%]
    test_example2.py::test_scope2 func_scope
    PASSED                                     [100%]

    ============================== 2 passed in 0.07s ==============================

```

> 从这里可以看出 module，session 作用域的固件只执行了一次，可以验证官方的使用介绍

### 自动执行

> 有人可能会说，这样子怎么那么麻烦，unittest 框架中直接定义 setUp 就能自动执行预处理，同样的 pytest 框架也有类似的自动执行； pytest 框架中固件一般通过参数 autouse 控制自动运行。

```python
    import pytest


    @pytest.fixture(scope='session', autouse=True)
    def connect_db():
       print("Connect Database in .......")
       yield
       print("Close Database out .......")


    def test1():
       print("test1")


    def test2():
       print("test")

```

执行结果：

```shell
    ============================= test session starts =============================
    platform win32 -- Python 3.6.8, pytest-6.2.5, py-1.10.0, pluggy-1.0.0 -- D:\Coding\Python3.6\python.exe
    cachedir: .pytest_cache
    rootdir: C:\Users\libuliduobuqiuqiu\Desktop\GitProjects\PythonDemo\pytest
    plugins: Faker-8.11.0
    collecting ... collected 2 items

    test_example.py::test1 Connect Database in .......
    PASSED                                            [ 50%]test1

    test_example.py::test2 PASSED                                            [100%]test
    Close Database out .......


    ============================== 2 passed in 0.07s ==============================

```

> 从结果看到，测试函数运行前后自动执行了 connect\_db 固件；

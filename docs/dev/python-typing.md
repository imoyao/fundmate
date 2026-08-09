---
title: 对你的代码进行类型提示
permalink: /dev/type-hints
---

## 返回类示例

* 在 Python 3.10 或以上版本，直接返回类即可；
* Python 3.7+: `from __future__ import annotations`

```python
from __future__ import annotations

class Position:
    def __add__(self, other: Position) -> Position:
        ...
```

* Python <3.7 版本: 使用类的`string`形式

```python
class Position:
    ...
    def __add__(self, other: 'Position') -> 'Position':
       ...

```

参阅：[python - How do I type hint a method with the type of the enclosing class? - Stack Overflow](https://stackoverflow.com/questions/33533148/how-do-i-type-hint-a-method-with-the-type-of-the-enclosing-class)

* Exceptions
 对于异常，目前没有建议列出显式引发的异常的语法。 而是建议将此信息文档化，放在代码的文档字符串中。
参阅：[PEP 484 -- Type Hints | Python.org](https://www.python.org/dev/peps/pep-0484/#id48)

## 相关链接

* [typing --- 类型提示支持 — Python 3.9.1 文档](https://docs.python.org/zh-cn/3/library/typing.html)
* [如何看待类型注解在 Python 中的前途？ - 知乎](https://www.zhihu.com/question/56167969)
* [为什么 TypeScript 如此流行，却少见有人写带类型标注的 Python？ - 知乎](https://www.zhihu.com/question/370231112)

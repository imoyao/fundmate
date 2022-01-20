---
title: 为SQLAlchemy创建choice数据类型
permalink: /dev/choices-for-sqlalchemy
---
## 引言
Django中的choices以及为什么要这个？

## 一种拙劣的实现方式

## 一种更好的实现方式
引入dataklass
```python
from dataklasses import dataklass

@dataklass
class ChoiceTypeIntegerDk:
    key: int
    value: str
    label: str

foo = ChoiceTypeIntegerDk(1,'bar','the foo explain of the bar.')
```
choice的`get_xx_display`方法我们可以直接使用`@property`装饰器返回，即此时代码为：
```python

@dataklass
class ChoiceTypeIntegerDk:
    key: int
    value: str
    label: str

    @property
    def display(self):
        return self.label
```
然后定义我们的数组
```python
@enum.unique
class RiskTypeEnum(enum.Enum):
    undefined = UNDEFINED
    plain = PLAIN
    low = LOW
    balance = BALANCE
    advance = ADVANCE
    high = HIGH
```
其中，我们的`@enum.unique`用于保证枚举元素无重复。

获取枚举类元素为
```python
baz = RiskTypeEnum
In [3]: baz.undefined.name
Out[3]: 'undefined'

In [4]: baz.undefined.value
Out[4]: ChoiceTypeIntegerDk(0, 'undefined', '未定义')

```
获取元素属性为
```python
In [5]: baz.undefined.value.key
Out[5]: 0

In [7]: baz.undefined.value.value
Out[7]: 'undefined'

In [8]: baz.undefined.value.label
Out[8]: '未定义'

In [9]: baz.undefined.value.display
Out[9]: '未定义'

```
这样有一个缺点是，太长了，获取路径太长，于是定义
```python
@enum.unique
class RiskTypeEnum(enum.Enum):
    undefined = UNDEFINED
    plain = PLAIN
    low = LOW
    balance = BALANCE
    advance = ADVANCE
    high = HIGH

    @DynamicClassAttribute
    def dk_name(self):
        """The name of the Enum member."""
        return self._name_

    @DynamicClassAttribute
    def dk_value(self):
        """The value of the Enum member."""
        return self._value_.key

    @DynamicClassAttribute
    def dk_display(self):
        """The value of the Enum member."""
        return self._value_.label
```
不复写的原因是我们可能需要获取`value`，此时：
````python
In [4]: baz.undefined.dk_display
Out[4]: '未定义'

In [5]: baz.undefined.dk_name
Out[5]: 'undefined'

In [6]: baz.undefined.name
Out[6]: 'undefined'

In [7]: baz.undefined.dk_value
Out[7]: 0

In [8]: baz.undefined.value
Out[8]: ChoiceTypeIntegerDk(0, 'undefined', '未定义')

````

## 定义数据库需要用到的数据类型

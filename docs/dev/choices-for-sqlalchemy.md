---
title: 为`SQLAlchemy`创建`choices`数据类型
permalink: /dev/choices-for-sqlalchemy
---
## 引言
用过Django的都知道，它的模型字段中有一个非常好用的字段类型`choices`：[模型字段`choices`参考 | Django 文档 | Django](https://docs.djangoproject.com/zh-hans/4.0/ref/models/fields/#choices) ，在3.0版本中，更进一步定义了[Enumerations for model field choices - Django 3.0 release notes | Django documentation | Django](https://docs.djangoproject.com/en/4.0/releases/3.0/#enumerations-for-model-field-choices) ，源码参考：[django/enums.py at main · django/django](https://github.com/django/django/blob/main/django/db/models/enums.py) 。
::: warning
那么我们为什么使用choices呢？
> Error prevention and logic separation.
参阅[此处](https://stackoverflow.com/a/32657683/14295718) 。

我们只需要修改model层定义的“常量”，而不需要在view层修改硬编码内容。即使常量被我们修改，通过IDE的自动探测功能，我们也能即使发现错误。
:::
## 一种拙劣的实现方式
基础数据定义
````python
# 风险等级
RISK_TYPE = {
    'undefined': 0,  # 未定义
    'plain': 1,  # 灵活取用
    'low': 2,  # 稳健增值
    'balance': 3,  # 平衡增长
    'advance': 4,  # 进阶成长
    'high': 5,  # 积极进取
}
# 风险等级显示
RISK_TYPE_DISPLAY = {
    'undefined': '未定义',
    'plain': '灵活取用',
    'low': '稳健增值',
    'balance': '平衡增长',
    'advance': '进阶成长',
    'high': '积极进取'
}
````
SQLAlchemy数据类型定义：
```python
from typing import Optional, Union
import sqlalchemy.types as types

class BaseChoice(types.TypeDecorator):
    cache_ok = False

    def process_bind_param(self, value, dialect):
        if value in self.choices_rev:
            return self.choices_rev[value]
        if value in self.choices:
            return value
        raise KeyError(f"Value not found in choices: {value}")

    def process_result_value(self, value, dialect):
        return self.choices[value]


class ChoiceTypeInteger(BaseChoice):
    """
    适用于key为int的
    """
    impl = types.Integer

    def __init__(self, choices: Union[list, tuple, dict], **kw):
        # 传的是int类型，则需要检查是否key为int,是才可以继续
        is_all_key_int = all([isinstance(i, int) for i in choices.keys()])
        if not is_all_key_int:
            raise KeyError("Key should be integer.")
        if len(choices) == 0:
            raise ValueError("No choices provided!")

        if isinstance(choices, list) or isinstance(choices, tuple):
            if isinstance(choices[0], str):
                choices = [(s, s) for s in choices]
            self.choices = dict(choices)
        elif isinstance(choices, dict):
            self.choices = choices
        num_choices = len(self.choices)
        if num_choices != len(set(self.choices.keys())):
            raise KeyError("Choice keys must be unique")
        if num_choices != len(set(self.choices.values())):
            raise ValueError("Choice values must be unique")
        self.choices_rev = key2val(self.choices)
        super().__init__(**kw)


class ChoiceType(BaseChoice):
    """
    适用于key为string的情况
    """
    '''
    String 报错： `sqlalchemy.exc.CompileError: VARCHAR requires a length on dialect mysql`
    `ChoiceType` 接受关键字参数`length`来自定义字符长度
    '''
    impl = types.String(60)

    def __init__(self, choices: Union[list, tuple, dict], **kw):
        if len(choices) == 0:
            raise ValueError("No choices provided!")

        if isinstance(choices, list) or isinstance(choices, tuple):
            if isinstance(choices[0], str):
                choices = [(s, s) for s in choices]
            self.choices = dict(choices)
        elif isinstance(choices, dict):
            self.choices = choices
        num_choices = len(self.choices)
        if num_choices != len(set(self.choices.keys())):
            raise KeyError("Choice keys must be unique")
        if num_choices != len(set(self.choices.values())):
            raise ValueError("Choice values must be unique")
        self.choices_rev = key2val(self.choices)
        super().__init__(**kw)

    def process_result_value(self, value, dialect):
        """
        key是str的直接返回即可
        :param value:
        :param dialect:
        :return:
        """
        return value


def key2val(unique_dict: dict) -> dict:
    return {v: k for k, v in unique_dict.items()}
```
[代码参考](https://github.com/imoyao/fundmate/blob/164ba18f8ff292b66a6767a1d29e7125f8ace38a/backend/fundmate/database.py#L233)
此时要使用数据类型：
```python
class Fund(PkModel, UpsertMixin):
    """基金表"""
    __tablename__ = 'funds'
    __table_args__ = {'comment': '基金表'}
    # TODO: 验证规则
    '''
    [《证券投资基金编码规范》实施细则](http://www.csisc.cn/zbscbzw/ywguize/201212/bf12c532a6c44cde864f59d9f2423f1b.shtml)
    [证券投资基金编码简介](http://www.csisc.cn/zbscbzw/cpbmjj/201212/f3263ab61f7c4dba8461ebbd9d0c6755.shtml)
    [证券投资基金编码规范](http://www.csisc.cn/zbscbzw/hyfbjcbmm/201904/d2587b8addb54335a87017af40344e24.shtml)
    [基金代码有什么规则？区分认购代码和交易代码 - 希财网](https://www.csai.cn/jijin/1298440.html)
    [基金代码含义及编制规则 - 知乎](https://zhuanlan.zhihu.com/p/24948157)
    '''
    fund_code = Column(db.String(6), unique=True, comment='基金编码')
    name = Column(db.String(30), comment='基金名称')
    '''
    此处标准写法应该使用英文，但是可能导致查询啰嗦，所以使用拼音代替变量，后面变量作为列名自解释
    1. [python - Use alias for column name in SQLAlchemy - Stack Overflow]
    (https://stackoverflow.com/questions/37758128/use-alias-for-column-name-in-sqlalchemy)
    2. [mysql - Aliasing field names in SQLAlchemy model or underlying SQL table - Stack Overflow]
    (https://stackoverflow.com/questions/37420135/aliasing-field-names-in-sqlalchemy-model-or-underlying-sql-table)
    查询：
    [SQLAlchemy select 中的表别名、列别名 | Jeremy's blog](https://www.isyin.cn/note/2018-10-28-2249/)
    ```
    # 表别名：select * from my_customer_table as customer
    customer = my_customer_table.alias('customer')
    # 列别名 select user.name as username from user
    columns = [
        customer,
        user.c['name'].label('username')
    ]
    ```
    '''
    ...
    symbol_prefix = Column(ChoiceType(choices=settings.SYMBOL_TYPE),
                           nullable=True,
                           default='UN',
                           comment='符号前缀（FP/SZ/SH）')
    risk_level = Column(ChoiceTypeInteger(choices=key2val(settings.RISK_TYPE)),
                        default=1,
                        nullable=True,
                        comment='风险等级')
    ...
```
为了显示解释性的文字信息，我们需要：
```python
# 其中display_map即为上文基础数据定义中的RISK_TYPE_DISPLAY
def display(display_map: dict, pk_key: str) -> str:
    """
    数据库中存的是数字，保存是输入拼音，显示时应为可读信息
    :param pk_key:
    :param display_map:
    :return:
    """
    return display_map.get(pk_key)
```
这样的定义可以实现我们的功能，但是不利于数据扩展。假设我们需要修改基础数据中的定义，那么，每一次都需要修改`XX_TYPE`(a)和`XX_TYPE_DISPLAY`(a)两个的定义，而且只能在字段定义的代码中检查key的唯一性，如果两个基础数据a和b拥有不同的key，那我们是没法感知到的。

## 一种更好的实现方式
仔细观察我们的数据定义，可以发现基础数据由`value`,`name`,`label`等属性构成，为了更加简明地定义这种数据，我们引入[dataklasses](https://github.com/dabeaz/dataklasses) ，关于它的基础用法请参考作者的说明文档。以下是我的定义：

### 定义基础数据
```python
from dataklasses import dataklass

@dataklass
class ChoiceTypeIntegerDk:
    value: int
    name: str
    label: str

foo = ChoiceTypeIntegerDk(1,'bar','the foo explain of the bar.')
```
`choices`的`get_xx_display`方法我们可以直接使用`@property`装饰器返回，即此时代码为：
```python

@dataklass
class ChoiceTypeIntegerDk:
    value: int
    name: str
    label: str

    @property
    def display(self):
        return self.label
```
:::tip
需要注意的是，当我们把所有的参数作为位置参数时，我们定义类的属性的顺序就是我们传参的顺序；当然，如果我们把参数当作关键字参数时，则顺序是可以随便调换的。
:::
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
其中，`@enum.unique`装饰器用于保证枚举元素无重复。

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
In [5]: baz.undefined.value.value
Out[5]: 0

In [7]: baz.undefined.value.name
Out[7]: 'undefined'

In [8]: baz.undefined.value.label
Out[8]: '未定义'

In [9]: baz.undefined.value.display
Out[9]: '未定义'

```
这样有一个缺点是，太长了，获取`value`属性路径太长，于是借助`DynamicClassAttribute`我们定义更多的属性方法。
```python
@enum.unique
class BaseTypeEnum(enum.Enum):

    def __str__(self):
        return f'My custom BaseTypeEnum {self.value}'

    @DynamicClassAttribute
    def dk_name(self):
        """The name of the Enum member."""
        try:
            return self._value_.name
        except AttributeError:
            raise AttributeError('Please use `dk_value` while value is instance of `ChoiceTypeDk`.')

    @DynamicClassAttribute
    def dk_value(self):
        """The value of the Enum member."""
        return self._value_.value

    @DynamicClassAttribute
    def label(self):
        """The label of the Enum member."""
        return self._value_.label

    @DynamicClassAttribute
    def dk_display(self):
        """alias of label"""
        return self.label

    @DynamicClassAttribute
    def display(self):
        """alias of label"""
        return self.label

    def describe(self):
        # self is the member here
        return self.name, self.value

    @classmethod
    def values(cls):
        """
        >>> r.values()
        [ChoiceTypeIntegerDk(0, 'undefined', '未定义'),
         ChoiceTypeIntegerDk(1, 'plain', '灵活取用'),
         ChoiceTypeIntegerDk(2, 'low', '稳健增值'),
         ChoiceTypeIntegerDk(3, 'balance', '平衡增长'),
         ChoiceTypeIntegerDk(4, 'advance', '进阶成长'),
         ChoiceTypeIntegerDk(5, 'high', '积极进取')]

        :return:
        """
        return [member.value for member in cls]

    @classmethod
    def names(cls):
        """
        只有当是value是int时才可以调用该方法，注意和定义类的`input`区分
        Example:
        >>> r.names()
        ['undefined', 'plain', 'low', 'balance', 'advance', 'high']

        :return:
        """
        empty = ['__empty__'] if hasattr(cls, '__empty__') else []
        return empty + [member.name for member in cls]

    @classmethod
    def labels(cls):
        """
        Example:
        >>> r = RiskTypeEnum
        >>> r.labels()
        ['未定义', '灵活取用', '稳健增值', '平衡增长', '进阶成长', '积极进取']
        :return:
        """
        return [member.label for member in cls]

    @classmethod
    def choices(cls):
        """
        >>> r = RiskTypeEnum
        >>> r.choices()
        [(0, '未定义'), (1, '灵活取用'), (2, '稳健增值'), (3, '平衡增长'), (4, '进阶成长'), (5, '积极进取')]

        :return:
        """
        empty = [(None, cls.__empty__)] if hasattr(cls, '__empty__') else []
        return empty + [(member.dk_value, member.label) for member in cls]

    @classmethod
    def comment(cls) -> str:
        """
        返回 key 和 label 对应的字典（字符串类型）
        :return:
        """
        enum_explains = dict()
        for name, member in cls.__members__.items():
            key = member.dk_value
            enum_explains[key] = member.dk_display
        return str(enum_explains)
```
不复写的原因是我们可能需要获取`value`。
在定义具体的`XXTypeEnum`时，我们继承`BaseTypeEnum`可以避免代码冗余。
```python
UNDEFINED = ChoiceTypeIntegerDk(0, 'undefined', '未定义')
PLAIN = ChoiceTypeIntegerDk(1, 'plain', '灵活取用')
LOW = ChoiceTypeIntegerDk(2, 'low', '稳健增值')
BALANCE = ChoiceTypeIntegerDk(3, 'balance', '平衡增长')
ADVANCE = ChoiceTypeIntegerDk(4, 'advance', '进阶成长')
HIGH = ChoiceTypeIntegerDk(5, 'high', '积极进取')


class RiskTypeEnum(BaseTypeEnum):
    """风险等级"""
    undefined = UNDEFINED
    plain = PLAIN
    low = LOW
    balance = BALANCE
    advance = ADVANCE
    high = HIGH

    @classmethod
    def default(cls):
        """
        默认值，如果要使用非默认的默认值，则调用普通赋值操作即可
        FIXME: py3.8+ [python - Using property() on classmethods - Stack Overflow](https://stackoverflow.com/questions/128573/using-property-on-classmethods)
        :return:
        """
        return cls.balance

    @classmethod
    def input(cls):
        """
        用户请求时需要用到
        **注意：**只有当key为int时才有name属性
        :return:
        """
        return [item.dk_name for item in cls]

```
此时：
````python
baz = RiskTypeEnum
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
### 定义数据库需要用到的数据类型
```python
class IntChoiceDkEnumType(ScalarCoercible, types.TypeDecorator):
    """
    存入数据中的值为int的自定义Enum类型
    """
    impl = db.Integer()

    cache_ok = True

    def __init__(self, choices, impl=None, **kwargs):
        self.choices = choices
        if Enum is not None and isinstance(choices, type) and issubclass(choices, Enum):
            self.type_impl = DkEnumTypeImpl(enum_class=choices)
        else:
            self.type_impl = ChoiceTypeImpl(choices=choices)

        if impl:
            self.impl = impl
        super().__init__(**kwargs)

    @property
    def python_type(self):
        return self.impl.python_type

    def _coerce(self, value):
        return self.type_impl._coerce(value)

    def process_bind_param(self, value, dialect):
        if isinstance(value, BaseTypeEnum):
            return value.dk_value
        return self.type_impl.process_bind_param(value, dialect)

    def process_result_value(self, value, dialect):
        return self.type_impl.process_result_value(value, dialect)


class DkEnumTypeImpl(object):

    def __init__(self, enum_class):
        if Enum is None:
            raise ImproperlyConfigured("'enum34' package is required to use 'EnumType' in Python " "< 3.4")
        if not issubclass(enum_class, Enum):
            raise ImproperlyConfigured("EnumType needs a class of enum defined.")
        # 组装一个字典，让保存在数据库中的int类型的key去获取对应的ChoiceTypeIntegerDk
        dk_enums = dict()
        for name, member in enum_class.__members__.items():
            key = member.dk_value  # int 作为key
            # enum_value = member.value  # item of enumeration 作为值
            dk_enums[key] = member
        self.enum_class = enum_class
        self.dk_enums = dk_enums

    def _coerce(self, value):
        if value is None:
            return None
        return self.dk_enums.get(value)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        elif isinstance(value, int):
            return self.dk_enums.get(value)
        if isinstance(value, str):
            enum_names = self.enum_class.names()
            if value in enum_names:
                dk_value = getattr(self.enum_class, value).dk_value
                return dk_value
            raise NotImplementedError('The key should be Enum of BaseTypeEnum.')

    def process_result_value(self, value, dialect):
        return self._coerce(value)

```
:::warning
由于使用alembic来实现数据库的改动迁移，我们自定义的数据库字段是没法自动识别的，所以需要修改`migrations`中的`env.py`参阅 [此处](https://stackoverflow.com/a/61320562/14295718) ；此外，通过定义`choices.py`我们实现最小改动下可以导入自定义数据，具体实现逻辑参阅`render_choice_type()`方法。
参阅 [此处](https://alembic.sqlalchemy.org/en/latest/autogenerate.html#affecting-the-rendering-of-types-themselves)
:::
### 字段使用
```python
class UserType(Enum):
    admin = 1
    regular = 2


class Test(PkModel):
    dk_test_str = Column(db.Enum(settings.SymbolTypeEnum),
                         nullable=True,
                         default=settings.SymbolTypeEnum.default().dk_value,
                         comment='符号前缀（FP/SZ/SH）')
    dk_safe_num = Column(SafeNumeric(8, 2), nullable=True, comment='SafeNumeric')
    user_type = Column(ChoiceType(UserType))
    risk_type = Column(IntChoiceDkEnumType(settings.RiskTypeEnum,
                                           default=settings.RiskTypeEnum.default().dk_value,
                                           impl=db.Integer()),
                       comment=settings.RiskTypeEnum.comment())
    op_type = Column(IntChoiceDkEnumType(settings.FundOpTypeEnum,
                                         default=settings.FundOpTypeEnum.default().dk_value,
                                         impl=db.Integer()),
                     comment=f'测试：{settings.FundOpTypeEnum.comment()}')

```
## 总结
基于dataklasses模块，我们实现了一种可以自定义复杂value的Enum类型，之后再定义`IntChoiceDkEnumType`供数据库定义时使用，这样保存的数据就可以按照我们预期的保存并有限地限制输入非法值的状况，从而实现错误预防和逻辑分离。

## 推荐阅读

- [Moving to Django 3.0’s Field.choices Enumeration Types - Adam Johnson](https://adamj.eu/tech/2020/01/27/moving-to-django-3-field-choices-enumeration-types/)
- [How to Create Django Like Choices Field in Flask SQLAlchemy | by Erika Dike | The Andela Way | Medium](https://medium.com/the-andela-way/how-to-create-django-like-choices-field-in-flask-sqlalchemy-1ca0e3a3af9d)
-     [Custom Types — SQLAlchemy 1.4 Documentation](https://docs.sqlalchemy.org/en/14/core/custom_types.html)

  [python - SQLAlchemy - How to make "django choices" using SQLAlchemy? - Stack Overflow](
  https://stackoverflow.com/questions/6262943/sqlalchemy-how-to-make-django-choices-using-sqlalchemy)

  [How to Create Django Like Choices Field in Flask SQLAlchemy | by Erika Dike | The Andela Way | Medium](
  https://medium.com/the-andela-way/how-to-create-django-like-choices-field-in-flask-sqlalchemy-1ca0e3a3af9d)

  [python - Best way to do enum in Sqlalchemy? - Stack Overflow](
  https://stackoverflow.com/questions/2676133/best-way-to-do-enum-in-sqlalchemy/2676213)

  [zzzeek : The Enum Recipe](https://techspot.zzzeek.org/2011/01/14/the-enum-recipe/)
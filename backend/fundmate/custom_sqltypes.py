#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@create: 2022/1/26 16:23
@file: custom_sqltypes.py
@author: imoyao
@email: immoyao@gmail.com
@desc: 为sqlalchemy自定义数据类型
参考：https://sqlalchemy-utils.readthedocs.io/en/latest/_modules/sqlalchemy_utils/types/choice.html#ChoiceType

## 示例代码
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
"""
from decimal import Decimal
from enum import Enum

import sqlalchemy.types as types

from backend.fundmate.database import db
from backend.fundmate.excepts import ImproperlyConfigured
from backend.fundmate.libs.dk_enums import BaseTypeEnum


class SafeNumeric(db.TypeDecorator):
    """sqlalchemy示例代码：Adds quantization to Numeric."""

    impl = db.Numeric(8, 2)

    def __init__(self, *arg, **kw):
        super().__init__(self, *arg, **kw)
        self.quantize_int = -self.impl.scale
        self.quantize = Decimal(10)**self.quantize_int

    def process_bind_param(self, value, dialect):
        if isinstance(value, Decimal) and \
                value.as_tuple()[2] < self.quantize_int:
            value = value.quantize(self.quantize)
        return value


class ScalarCoercible:
    cache_ok = True

    def _coerce(self, value):
        raise NotImplementedError

    def coercion_listener(self, target, value, oldvalue, initiator):
        return self._coerce(value)


class Choice(object):

    def __init__(self, code, value):
        self.code = code
        self.value = value

    def __eq__(self, other):
        if isinstance(other, Choice):
            return self.code == other.code
        return other == self.code

    def __hash__(self):
        return hash(self.code)

    def __ne__(self, other):
        return not (self == other)

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return 'Choice(code={code}, value={value})'.format(code=self.code, value=self.value)


class ChoiceTypeImpl(object):
    """The implementation for the ``Choice`` usage."""

    def __init__(self, choices):
        if not choices:
            raise ImproperlyConfigured('ChoiceType needs list of choices defined.')
        self.choices_dict = dict(choices)

    def _coerce(self, value):
        if value is None:
            return value
        if isinstance(value, Choice):
            return value
        return Choice(value, self.choices_dict[value])

    def process_bind_param(self, value, dialect):
        if value and isinstance(value, Choice):
            return value.code
        return value

    def process_result_value(self, value, dialect):
        if value:
            return Choice(value, self.choices_dict[value])
        return value


class EnumTypeImpl(object):
    """The implementation for the ``Enum`` usage."""

    def __init__(self, enum_class):
        if Enum is None:
            raise ImproperlyConfigured("'enum34' package is required to use 'EnumType' in Python " "< 3.4")
        if not issubclass(enum_class, Enum):
            raise ImproperlyConfigured("EnumType needs a class of enum defined.")

        self.enum_class = enum_class

    def _coerce(self, value):
        if value is None:
            return None
        ret_value = getattr(self.enum_class, value)
        return ret_value

    def process_bind_param(self, value, dialect):
        """
        保存的是enum对象的 `name`
        :param value:
        :param dialect:
        :return:
        """
        if value is None:
            return None
        # 如果输入的key是enum的name，可以认为也是合法值
        if isinstance(value, str):
            enum_names = self.enum_class.names()
            if value in enum_names:
                return value
            raise NotImplementedError('The key should be Enum of BaseTypeEnum.')

        return self.enum_class(value).name

    def process_result_value(self, value, dialect):
        return self._coerce(value)


class ChoiceType(ScalarCoercible, types.TypeDecorator):
    """
    ChoiceType offers way of having fixed set of choices for given column. It
    could work with a list of tuple (a collection of key-value pairs), or
    integrate with :mod:`enum` in the standard library of Python 3.4+ (the
    enum34_ backported package on PyPI is compatible too for ``< 3.4``).

    .. _enum34: https://pypi.python.org/pypi/enum34

    Columns with ChoiceTypes are automatically coerced to Choice objects while
    a list of tuple been passed to the constructor. If a subclass of
    :class:`enum.Enum` is passed, columns will be coerced to :class:`enum.Enum`
    objects instead.

    ::

        class User(Base):
            TYPES = [
                (u'admin', u'Admin'),
                (u'regular-user', u'Regular user')
            ]

            __tablename__ = 'user'
            id = sa.Column(sa.Integer, primary_key=True)
            name = sa.Column(sa.Unicode(255))
            type = sa.Column(ChoiceType(TYPES))


        user = User(type=u'admin')
        user.type  # Choice(code='admin', value=u'Admin')

    Or::

        import enum


        class UserType(enum.Enum):
            admin = 1
            regular = 2


        class User(Base):
            __tablename__ = 'user'
            id = sa.Column(sa.Integer, primary_key=True)
            name = sa.Column(sa.Unicode(255))
            type = sa.Column(ChoiceType(UserType, impl=sa.Integer()))


        user = User(type=1)
        user.type  # <UserType.admin: 1>


    ChoiceType is very useful when the rendered values change based on user's locale:

    ::

        from babel import lazy_gettext as _


        class User(Base):
            TYPES = [
                (u'admin', _(u'Admin')),
                (u'regular-user', _(u'Regular user'))
            ]

            __tablename__ = 'user'
            id = sa.Column(sa.Integer, primary_key=True)
            name = sa.Column(sa.Unicode(255))
            type = sa.Column(ChoiceType(TYPES))


        user = User(type=u'admin')
        user.type  # Choice(code='admin', value=u'Admin')

        print user.type  # u'Admin'

    Or::

        from enum import Enum
        from babel import lazy_gettext as _


        class UserType(Enum):
            admin = 1
            regular = 2


        UserType.admin.label = _(u'Admin')
        UserType.regular.label = _(u'Regular user')


        class User(Base):
            __tablename__ = 'user'
            id = sa.Column(sa.Integer, primary_key=True)
            name = sa.Column(sa.Unicode(255))
            type = sa.Column(ChoiceType(UserType, impl=sa.Integer()))


        user = User(type=UserType.admin)
        user.type  # <UserType.admin: 1>

        print user.type.label  # u'Admin'

    参考:
    https://github.com/flask-admin/flask-admin/issues/1134#issuecomment-361821787

    [Data types — SQLAlchemy-Utils 0.37.8 documentation]
    (https://sqlalchemy-utils.readthedocs.io/en/latest/data_types.html#module-sqlalchemy_utils.types.choice)

    refs:
    [Custom Types — SQLAlchemy 1.4 Documentation](https://docs.sqlalchemy.org/en/14/core/custom_types.html)

    [python - SQLAlchemy - How to make "django choices" using SQLAlchemy? - Stack Overflow](
    https://stackoverflow.com/questions/6262943/sqlalchemy-how-to-make-django-choices-using-sqlalchemy)

    [How to Create Django Like Choices Field in Flask SQLAlchemy | by Erika Dike | The Andela Way | Medium](
    https://medium.com/the-andela-way/how-to-create-django-like-choices-field-in-flask-sqlalchemy-1ca0e3a3af9d)

    [python - Best way to do enum in Sqlalchemy? - Stack Overflow](
    https://stackoverflow.com/questions/2676133/best-way-to-do-enum-in-sqlalchemy/2676213)

    [zzzeek : The Enum Recipe](https://techspot.zzzeek.org/2011/01/14/the-enum-recipe/)
    """
    impl = types.String(255)

    cache_ok = True

    def __init__(self, choices, impl=None, **kwargs):
        self.choices = tuple(choices) if isinstance(choices, list) else choices
        if Enum is not None and isinstance(choices, type) and issubclass(choices, Enum):
            self.type_impl = EnumTypeImpl(enum_class=choices)
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
        return self.type_impl.process_bind_param(value, dialect)

    def process_result_value(self, value, dialect):
        return self.type_impl.process_result_value(value, dialect)


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

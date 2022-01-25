# -*- coding: utf-8 -*-
"""Database module, including the SQLAlchemy database object and DB-related utilities."""
import enum
import random
from datetime import datetime
from decimal import Decimal
from enum import Enum, EnumMeta
from typing import Optional, Union

from apiflask import pagination_builder

import sqlalchemy.types as types
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

from backend.fundmate.compat import basestring
from backend.fundmate.excepts import UniqueInstanceError
from backend.fundmate.extensions import db
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.settings import BaseTypeEnum, ChoiceTypeDk, ChoiceTypeIntegerDk

# Alias common SQLAlchemy names
Column = db.Column
relationship = db.relationship
Base = declarative_base()


class CRUDMixin(object):
    """Mixin that adds convenience methods for CRUD (create, read, update, delete) operations."""

    @classmethod
    def create(cls, **kwargs):
        """Create a new record and save it the database."""
        commit = kwargs.pop('synchronize_session', True)
        instance = cls(**kwargs)
        instance.save(commit=commit)
        return instance

    def update(self, commit: bool = True, **kwargs):
        """Update specific fields of a record."""
        for attr, value in kwargs.items():
            setattr(self, attr, value)
        if commit:
            db.session.commit()
        return self

    def save(self, commit: bool = True):
        """Save the record."""
        db.session.add(self)
        if commit:
            '''
            Flask-SQLAlchemy提供了一个SQLALCHEMY_COMMIT_ON_TEARDOWN配置变量，
            将其设为True可以设置自动调用commit()方法提交数据库会话。
            因为存在潜在的Bug，目前已不建议使用，而且未来版本中将移除该配置变量。
            请避免使用该配置变量，可使用手动调用db.session.commit()方法的方式提交数据库会话。
            '''
            try:
                db.session.commit()
            except SQLAlchemyError as e:
                logger.error(e)
                db.session.rollback()
        return self

    def delete(self, commit: bool = True):
        """Remove the record from the database."""
        db.session.delete(self)
        return commit and db.session.commit()

    @classmethod
    def paginate_query(cls, query_args):
        pagination = cls.query.paginate(page=query_args['page'], per_page=query_args['per_page'])
        _items = pagination.items
        return {'items': _items, 'pagination': pagination_builder(pagination)}


class UpsertMixin(CRUDMixin):
    """
    **注意**，is_exist 方法应该查询的key必须保证唯一性
    1. 检查存在
    2. 存在则更新，不存在则插入
    我们可以重写is_exist 方法以实现混用，
    参阅：
    1. [python - SQLAlchemy insert or update example - Stack Overflow]
    (https://stackoverflow.com/questions/7889183/sqlalchemy-insert-or-update-example/18244144)
    2. [MySQL — SQLAlchemy 1.3 Documentation]
    (https://docs.sqlalchemy.org/en/13/dialects/mysql.html#insert-on-duplicate-key-update-upsert)
    """  # noqa: F501

    @classmethod
    def check_is_exists(cls, unique_query_arg: dict) -> bool:
        """
        根据unique_arg查询对象query_key是否存在
        :param unique_query_arg:
        :return:
        """
        # see also: https://stackoverflow.com/a/41951905
        is_exist = db.session.query(cls.query.filter_by(**unique_query_arg).exists()).scalar()
        return is_exist

    @classmethod
    def insert_or_update(cls, unique_query_arg: dict, do_log_flag: bool = False, **kwargs: Union[list, dict]):
        """
        创建或更新
        '''
        see also:django.db.models.query.QuerySet.update_or_create
        Looks up an object with the given kwargs, updating one with defaults
        if it exists, otherwise creates a new one.
        Returns a tuple (object, created), where created is a boolean
        specifying whether an object was created.
        '''
        :param unique_query_arg:查询出来的结果必须是unique的
        :param do_log_flag:是否记录日志
        :return:
        """
        # 更新或创建的时候，更新的数据不能为空
        if not kwargs:
            raise ValueError(f'Update kwargs should not be {kwargs}.')

        is_inst_exists = cls.check_is_exists(unique_query_arg)
        if is_inst_exists:
            # 允许多个查询条件 TODO: 如何写使之可以使用比较运算符 [python - sqlalchemy dynamic filtering - Stack Overflow](
            #  https://stackoverflow.com/questions/41305129/sqlalchemy-dynamic-filtering/41309069#41309069)

            result = cls.query.filter_by(**unique_query_arg).all()

            if len(result) == 1:
                inst = result[0]
                inst.update(kwargs)
                db.session.commit()
                if do_log_flag:
                    logger.success(f'{inst} has been UPDATED successful.')
            else:
                raise UniqueInstanceError(f'The query result:{result} get the count of instance more than 1.')

        else:
            inst = cls.create(**kwargs)
            if do_log_flag:
                logger.success(f'{inst} has been CREATED successful.')
        return inst


class Model(CRUDMixin, db.Model):
    """Base model class that includes CRUD convenience methods."""

    __abstract__ = True

    def to_dict(self):
        columns = self.__table__.columns.keys()
        return {key: getattr(self, key) for key in columns}


class PkModel(Model):
    """Base model class that includes CRUD convenience methods, plus adds a 'primary key' column named ``id``."""

    __abstract__ = True
    id = Column(db.Integer, primary_key=True)

    # def __repr__(self) -> str:
    #     return self._repr(id=self.id)
    #
    # def _repr(self, **fields: Dict[str, Any]) -> str:
    #     '''
    #     see also:[python - SQLAlchemy best way to define __repr__ for large tables - Stack Overflow]
    #     (https://stackoverflow.com/questions/55713664/sqlalchemy-best-way-to-define-repr-for-large-tables)
    #     Helper for __repr__
    #     '''
    #     field_strings = []
    #     at_least_one_attached_attribute = False
    #     for key, field in fields.items():
    #         try:
    #             field_strings.append(f'{key}={field!r}')
    #         except sa.orm.exc.DetachedInstanceError:
    #             field_strings.append(f'{key}=DetachedInstanceError')
    #         else:
    #             at_least_one_attached_attribute = True
    #     if at_least_one_attached_attribute:
    #         return f"<{self.__class__.__name__}({','.join(field_strings)})>"
    #     return f"<{self.__class__.__name__} {id(self)}>"

    @classmethod
    def get_by_id(cls, record_id):
        """Get record by ID."""
        if any((
                isinstance(record_id, basestring) and record_id.isdigit(),
                isinstance(record_id, (int, float)),
        )):
            return cls.query.get_or_404(int(record_id))
        return None


class CreateDateModel(Model):
    """模仿PkModel，给数据表增加一个创建日期列"""
    '''
    https://stackoverflow.com/a/18675245/14295718
    该指令用于不应映射到数据库表的抽象类
    '''
    __abstract__ = True
    '''
    使用server_default，即使不传值，数据库也会使用系统时间传默认值
    参阅：[python - SQLAlchemy default DateTime - Stack Overflow](https://stackoverflow.com/
    questions/13370317/sqlalchemy-default-datetime)
    '''
    create_at = Column(db.DateTime(timezone=True), default=datetime.now, server_default=func.now(), comment='创建时间')


def reference_col(tablename: str,
                  nullable: bool = False,
                  pk_name: str = "id",
                  foreign_key_kwargs: Union[dict, None] = None,
                  column_kwargs: Union[dict, None] = None):
    """
    Column that adds primary key foreign key reference.

    Usage: ::

        category_id = reference_col('category')
        category = relationship('Category', backref='categories')

    :param tablename: 外键指向表的表名
    :param nullable: 是否可以为空
    :param pk_name: 主键名
    :param foreign_key_kwargs: 外键参数
    :param column_kwargs: 列参数，如comment
    :return:
    """
    foreign_key_kwargs = foreign_key_kwargs or {}
    column_kwargs = column_kwargs or {}

    return Column(
        db.ForeignKey(f"{tablename}.{pk_name}", **foreign_key_kwargs),
        nullable=nullable,
        **column_kwargs,
    )


class BaseChoice(types.TypeDecorator):
    """
    https://github.com/flask-admin/flask-admin/issues/1134#issuecomment-361821787
    用法：
    ---
    ## A
    TYPES = [
        (u'admin', u'Admin'),
        (u'regular-user', u'Regular user')
    ]

    filed::
        type = db.Column(db.ChoiceType(length=xx, choices=TYPES))

    user = User(type=u'admin')
    user.type  # Choice(code='admin', value=u'Admin')

    ## B
    import enum

    class UserType(enum.Enum):
        admin = 1
        regular = 2

    type = sa.Column(ChoiceType(UserType, impl=sa.Integer()))


    user = User(type=1)
    user.type  # <UserType.admin: 1>

    ## C
    from enum import Enum
    from babel import lazy_gettext as _


    class UserType(Enum):
        admin = 1
        regular = 2


    UserType.admin.label = _(u'Admin')
    UserType.regular.label = _(u'Regular user')

    type = sa.Column(ChoiceType(UserType, impl=sa.Integer()))


    user = User(type=UserType.admin)
    user.type  # <UserType.admin: 1>

    print(user.type.label)  # u'Admin'
    ---
    参考:
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
    ''':type bool
    SAWarning: TypeDecorator ChoiceTypeInteger() will not produce a cache key because the ``cache_ok`` flag is not 
    set to True.  Set this flag to True if this type object's state is safe to use in a cache key, 
    or False to disable this warning.
    '''
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


# class ChoiceType(BaseChoice):
#     """
#     适用于key为string的情况
#     """
#     '''
#     String 报错： `sqlalchemy.exc.CompileError: VARCHAR requires a length on dialect mysql`
#     `ChoiceType` 接受关键字参数`length`来自定义字符长度
#     '''
#     impl = types.String(60)
#
#     def __init__(self, choices: Union[list, tuple, dict], **kw):
#         if len(choices) == 0:
#             raise ValueError("No choices provided!")
#
#         if isinstance(choices, list) or isinstance(choices, tuple):
#             if isinstance(choices[0], str):
#                 choices = [(s, s) for s in choices]
#             self.choices = dict(choices)
#         elif isinstance(choices, dict):
#             self.choices = choices
#         num_choices = len(self.choices)
#         if num_choices != len(set(self.choices.keys())):
#             raise KeyError("Choice keys must be unique")
#         if num_choices != len(set(self.choices.values())):
#             raise ValueError("Choice values must be unique")
#         self.choices_rev = key2val(self.choices)
#         super().__init__(**kw)
#
#     def process_result_value(self, value, dialect):
#         """
#         key是str的直接返回即可
#         :param value:
#         :param dialect:
#         :return:
#         """
#         return value


def key2val(unique_dict: dict) -> dict:
    return {v: k for k, v in unique_dict.items()}


class DkBaseChoiceEnum(db.TypeDecorator):
    cache_ok = False

    def process_bind_param(self, value, dialect):
        if isinstance(value, Enum):
            return value
        elif isinstance(value, int):
            return value
        return value.value

    def process_result_value(self, value, dialect):
        return self.choices[value]


class DkChoiceTypeInteger(DkBaseChoiceEnum):
    impl = db.Integer()

    def __init__(self, enumtype, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._enumtype = enumtype

    def process_bind_param(self, value, dialect):
        if isinstance(value, Enum):
            return value
        elif isinstance(value, int):
            return value
        return value.value

    def process_result_value(self, value, dialect):
        return self._enumtype(value)


class DkChoiceType(DkBaseChoiceEnum):
    impl = types.String(60)

    def __init__(self, enumtype, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._enumtype = enumtype

    def process_bind_param(self, value, dialect):
        if isinstance(value, Enum):
            return value
        elif isinstance(value, int):
            return value
        return value.value

    def process_result_value(self, value, dialect):
        return value


class SafeNumeric(db.TypeDecorator):
    """Adds quantization to Numeric."""

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


class ImproperlyConfigured(Exception):
    """
    FIXME: 测试通过后移动到excepts中
    SQLAlchemy-Utils is improperly configured; normally due to usage of
    a utility that depends on a missing library.
    """
    pass


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
            enum_names = [item.name for item in self.enum_class]
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


class IntChoiceType(ScalarCoercible, types.TypeDecorator):
    """
    存入数据中的值为int
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
            enum_value = member.value  # ChoiceTypeIntegerDk() 作为值
            dk_enums[key] = enum_value
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
            enum_names = [item.name for item in self.enum_class]
            if value in enum_names:
                dk_value = getattr(self.enum_class, value).dk_value
                return dk_value
            raise NotImplementedError('The key should be Enum of BaseTypeEnum.')

    def process_result_value(self, value, dialect):
        return self._coerce(value)


def get_table_name(model_cls_name):
    """
    如果类名变了，我们的编辑器可以自动发现错误并提示，但如果是写死的字符串，可能写入的数据会有问题

    see also: [python - How to discover table properties from SQLAlchemy mapped object - Stack Overflow](
    https://stackoverflow.com/questions/2441796/how-to-discover-table-properties-from-sqlalchemy-mapped-object)
    :param model_cls_name: :return:
    """
    return model_cls_name.__table__.name


def gen_digit_code(max_code: str, init_identifier: str, min_len: int = 6) -> Optional[str]:
    """
    生成递增n位识别号
    :return:
    """
    fp_identifier = init_identifier
    max_identifier = db.session.query(func.max(max_code)).one_or_none()
    if max_identifier != (None, ):
        max_num = max_identifier[0]
        if max_num is not None:
            increase_int = random.randrange(1, 3)
            fp_identifier = int(max_num) + increase_int
            return f'{fp_identifier:0{min_len}}'
    return fp_identifier

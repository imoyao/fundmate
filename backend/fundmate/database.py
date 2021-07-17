# -*- coding: utf-8 -*-
"""Database module, including the SQLAlchemy database object and DB-related utilities."""
import re
from datetime import datetime
from typing import Union

from apiflask import pagination_builder
from sqlalchemy import __version__
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.types import Enum, SchemaType, TypeDecorator

from .compat import basestring
from .extensions import db

# Alias common SQLAlchemy names
Column = db.Column
relationship = db.relationship
Base = declarative_base()


class CRUDMixin(object):
    """Mixin that adds convenience methods for CRUD (create, read, update, delete) operations."""

    @classmethod
    def create(cls, **kwargs):
        """Create a new record and save it the database."""
        instance = cls(**kwargs)
        return instance.save()

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
            Flask-SQLAlchemy提供了一个SQLALCHEMY_COMMIT_ON_TEARDOWN配置变量，将其设为True可以设置自动调用commit()方法提交数据库会话。因为存在潜在的Bug，目前已不建议使用，而且未来版本中将移除该配置变量。请避免使用该配置变量，可使用手动调用db.session.commit()方法的方式提交数据库会话。
            '''
            db.session.commit()
        return self

    def delete(self, commit: bool = True):
        """Remove the record from the database."""
        db.session.delete(self)
        return commit and db.session.commit()

    @classmethod
    def paginate_query(cls, query_args):
        pagination = cls.query.paginate(page=query_args['page'],
                                        per_page=query_args['per_page'])
        _items = pagination.items
        return {'items': _items, 'pagination': pagination_builder(pagination)}


class UpsertMixin(CRUDMixin):
    """
    **注意**，is_exist 方法应该查询的key必须保证唯一性
    1. 检查存在
    2. 存在则更新，不存在则插入
    我们可以重写is_exist 方法以实现混用，
    参阅：
    1. [python - SQLAlchemy insert or update example - Stack Overflow](https://stackoverflow.com/questions/7889183/sqlalchemy-insert-or-update-example/18244144)
    2. [MySQL — SQLAlchemy 1.3 Documentation](https://docs.sqlalchemy.org/en/13/dialects/mysql.html#insert-on-duplicate-key-update-upsert)
    """

    @classmethod
    def check_is_exists(cls, unique_query_arg: dict) -> bool:
        """
        根据unique_arg查询对象query_key是否存在
        :param unique_query_arg:
        :return:
        """
        # https://stackoverflow.com/a/41951905
        for attr, value in unique_query_arg.items():
            exists = db.session.query(
                cls.query.filter(
                    getattr(cls, attr) == value).exists()).scalar()
            if exists:  # TODO: what if unique_query_arg
                return exists
        return False

    @classmethod
    def insert_or_update(cls, unique_query_arg: dict, **kwargs: Union[list,
                                                                      dict]):
        """
        创建或更新
        :param unique_query_arg:
        :param kwargs:
        :return:
        """
        is_comp_exists = cls.check_is_exists(unique_query_arg)
        if is_comp_exists:
            # 允许多个查询条件 TODO: 可以使用比较运算符
            # [python - sqlalchemy dynamic filtering - Stack Overflow](https://stackoverflow.com/questions/41305129/sqlalchemy-dynamic-filtering/41309069#41309069)
            for attr, value in unique_query_arg.items():
                ret = cls.query.filter(
                    getattr(cls, attr) == value).update(kwargs)
            db.session.commit()
        else:
            ret = cls.create(**kwargs)
        return ret


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
    """模仿PkModel，给数据表增加一个添加创建时间列"""
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
    create_at = Column(db.DateTime(timezone=True),
                       default=datetime.now,
                       server_default=func.now(),
                       comment='创建时间')


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


class EnumSymbol(object):
    """Define a fixed symbol tied to a parent class.
    """

    def __init__(self, cls_, name, value, description):
        if __version__ < '0.6.5':
            raise NotImplementedError(
                "Version 0.6.5 or higher of SQLAlchemy is required.")
        self.cls_ = cls_
        self.name = name
        self.value = value
        self.description = description

    def __reduce__(self):
        """Allow unpickling to return the symbol
        linked to the DeclEnum class."""
        return getattr, (self.cls_, self.name)

    def __iter__(self):
        return iter([self.value, self.description])

    def __repr__(self):
        return "<%s>" % self.name


class EnumMeta(type):
    """Generate new DeclEnum classes."""

    def __init__(cls, classname, bases, dict_):
        cls._reg = reg = cls._reg.copy()
        for k, v in dict_.items():
            if isinstance(v, tuple):
                sym = reg[v[0]] = EnumSymbol(cls, k, *v)
                setattr(cls, k, sym)
        type.__init__(cls, classname, bases, dict_)

    def __iter__(cls):
        return iter(cls._reg.values())


class DeclEnumType(SchemaType, TypeDecorator):
    """
    TypeDecorator：对于那些没有使用过它的人来说，是提供一个围绕普通数据库类型的包装器，以提供额外的封送处理行为，这超出了我们从 DBAPI 获得一致性所需的行为。
    Impl数据成员指的是被包装的类型。在这种情况下，DeclEnumType 使用给定 DeclEnum 子类的信息生成一个新的 Enum
    对象。枚举的名称来自我们类的名称，使用世界上最短的驼峰式大小写到下划线（camel-case-to-underscore ）转换器。
    """

    def __init__(self, enum):
        super().__init__()
        self.enum = enum
        self.impl = Enum(*enum.values(),
                         name="ck%s" %
                         re.sub('([A-Z])', lambda m: "_" + m.group(1).lower(),
                                enum.__name__))

    def _set_table(self, table, column):
        self.impl._set_table(table, column)

    def copy(self):
        return DeclEnumType(self.enum)

    def process_bind_param(self, value, dialect):
        if value is not None:
            return value.value

    def process_result_value(self, value, dialect):
        if value is not None:
            return self.enum.from_string(value.strip())


class DeclEnum(object):
    """Declarative enumeration.
    参考下方链接
    [zzzeek : The Enum Recipe](https://techspot.zzzeek.org/2011/01/14/the-enum-recipe/)
    
    [python - SQLAlchemy - How to make "django choices" using SQLAlchemy? - Stack Overflow](
    https://stackoverflow.com/questions/6262943/sqlalchemy-how-to-make-django-choices-using-sqlalchemy)

    [How to Create Django Like Choices Field in Flask SQLAlchemy | by Erika Dike | The Andela Way | Medium](
    https://medium.com/the-andela-way/how-to-create-django-like-choices-field-in-flask-sqlalchemy-1ca0e3a3af9d)
    
    模仿Django的choice实现一个下拉选择的功能

    Examples:
    ```
    from sqlalchemy import Column, Integer, String, create_engine
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import Session

    Base = declarative_base()


    class EmployeeType(DeclEnum):
        part_time = "P", "Part Time"
        full_time = "F", "Full Time"
        contractor = "C", "Contractor"


    class Employee(Base):
        __tablename__ = 'employee'

        id = Column(Integer, primary_key=True)
        name = Column(String(60), nullable=False)
        type = Column(EmployeeType.db_type())

        def __repr__(self):
            return "Employee(%r, %r)" % (self.name, self.type)


    e = create_engine('sqlite://', echo=True)
    Base.metadata.create_all(e)

    sess = Session(e)

    sess.add_all([
        Employee(name='e1', type=EmployeeType.full_time),
        Employee(name='e2', type=EmployeeType.full_time),
        Employee(name='e3', type=EmployeeType.part_time),
        Employee(name='e4', type=EmployeeType.contractor),
        Employee(name='e5', type=EmployeeType.contractor),
    ])
    sess.commit()

    print(sess.query(Employee).filter_by(type=EmployeeType.contractor).all())
    ```
    """

    __metaclass__ = EnumMeta
    _reg = {}

    @classmethod
    def from_string(cls, value):
        try:
            return cls._reg[value]
        except KeyError:
            raise ValueError("Invalid value for %r: %r" %
                             (cls.__name__, value))

    @classmethod
    def values(cls):
        return cls._reg.keys()

    @classmethod
    def db_type(cls):
        return DeclEnumType(cls)

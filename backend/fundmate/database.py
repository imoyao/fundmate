# -*- coding: utf-8 -*-
"""Database module, including the SQLAlchemy database object and DB-related utilities."""
from datetime import datetime
from typing import Union

import sqlalchemy.types as types
from apiflask import pagination_builder
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

from backend.fundmate.compat import basestring
from backend.fundmate.extensions import db
from backend.fundmate.exts.flask_loguru import logger

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
    1. [python - SQLAlchemy insert or update example - Stack Overflow](https://stackoverflow.com/questions/7889183/sqlalchemy-insert-or-update-example/18244144)
    2. [MySQL — SQLAlchemy 1.3 Documentation](https://docs.sqlalchemy.org/en/13/dialects/mysql.html#insert-on-duplicate-key-update-upsert)
    """  # noqa: F501

    @classmethod
    def check_is_exists(cls, unique_query_arg: dict) -> bool:
        """
        根据unique_arg查询对象query_key是否存在
        :param unique_query_arg:
        :return:
        """
        # https://stackoverflow.com/a/41951905
        for attr, value in unique_query_arg.items():
            exists = db.session.query(cls.query.filter(getattr(cls, attr) == value).exists()).scalar()
            if exists:  # TODO: 如果请求的参数是 unique_query_arg
                return exists
        return False

    @classmethod
    def insert_or_update(cls, unique_query_arg: dict, **kwargs: Union[list, dict]):
        """
        创建或更新
        :param unique_query_arg:
        :param kwargs:
        :return:
        """
        ret = None
        is_inst_exists = cls.check_is_exists(unique_query_arg)
        if is_inst_exists:
            # 允许多个查询条件 TODO: 可以使用比较运算符 [python - sqlalchemy dynamic filtering - Stack Overflow](
            #  https://stackoverflow.com/questions/41305129/sqlalchemy-dynamic-filtering/41309069#41309069)
            for attr, value in unique_query_arg.items():
                ret = cls.query.filter(getattr(cls, attr) == value).update(kwargs)  # TODO:ret = 1
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


class ChoiceType(types.TypeDecorator):  # noqa
    """
    [zzzeek : The Enum Recipe](https://techspot.zzzeek.org/2011/01/14/the-enum-recipe/)

    [python - SQLAlchemy - How to make "django choices" using SQLAlchemy? - Stack Overflow](
    https://stackoverflow.com/questions/6262943/sqlalchemy-how-to-make-django-choices-using-sqlalchemy)

    [How to Create Django Like Choices Field in Flask SQLAlchemy | by Erika Dike | The Andela Way | Medium](
    https://medium.com/the-andela-way/how-to-create-django-like-choices-field-in-flask-sqlalchemy-1ca0e3a3af9d)

    [python - Best way to do enum in Sqlalchemy? - Stack Overflow](
    https://stackoverflow.com/questions/2676133/best-way-to-do-enum-in-sqlalchemy/2676213)
    """

    impl = types.String

    def __init__(self, choices, **kw):
        self.choices = dict(choices)
        super().__init__(**kw)

    def process_bind_param(self, value, dialect):
        return [k for k, v in self.choices.items() if v == value][0]

    def process_result_value(self, value, dialect):
        return self.choices[value]

# -*- coding: utf-8 -*-
"""Database module, including the SQLAlchemy database object and DB-related utilities."""
from datetime import datetime
from typing import Union
from apiflask import pagination_builder
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

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

    def update(self, commit=True, **kwargs):
        """Update specific fields of a record."""
        for attr, value in kwargs.items():
            setattr(self, attr, value)
        return commit and self.save() or self

    def save(self, commit=True):
        """Save the record."""
        db.session.add(self)
        if commit:
            '''
            Flask-SQLAlchemy提供了一个SQLALCHEMY_COMMIT_ON_TEARDOWN配置变量，将其设为True可以设置自动调用commit()方法提交数据库会话。因为存在潜在的Bug，目前已不建议使用，而且未来版本中将移除该配置变量。请避免使用该配置变量，可使用手动调用db.session.commit()方法的方式提交数据库会话。
            '''
            db.session.commit()
        return self

    def delete(self, commit=True):
        """Remove the record from the database."""
        db.session.delete(self)
        return commit and db.session.commit()

    @classmethod
    def paginate_query(cls, query_args):
        pagination = cls.query.paginate(
            page=query_args['page'],
            per_page=query_args['per_page']
        )
        _items = pagination.items
        return {
            'items': _items,
            'pagination': pagination_builder(pagination)
        }


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
        if any(
                (
                        isinstance(record_id, basestring) and record_id.isdigit(),
                        isinstance(record_id, (int, float)),
                )
        ):
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
    create_at = Column(db.DateTime(timezone=True), default=datetime.now, server_default=func.now(), comment='创建时间')


def reference_col(
        tablename: str, nullable: bool = False, pk_name: str = "id", foreign_key_kwargs: Union[dict, None] = None,
        column_kwargs: Union[dict, None] = None
):
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

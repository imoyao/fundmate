# -*- coding: utf-8 -*-
"""
Database module, including the SQLAlchemy database object and DB-related utilities.
"""
import random
from datetime import datetime
from typing import Optional, Union

from apiflask import pagination_builder

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

from backend.fundmate import utils
from backend.fundmate.compat import basestring
from backend.fundmate.excepts import UniqueInstanceError
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
        commit = kwargs.pop('synchronize_session', True)
        instance = cls(**kwargs)
        instance.save(commit=commit)
        return instance

    def update(self, commit: bool = True, **kwargs):
        """Update specific fields of a record."""
        for attr, value in kwargs.items():
            setattr(self, attr, value)
        self.save(commit=commit)
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
                logger.error(f'对象{self}保存数据出错 ERROR:{str(e)}')
                db.session.rollback()
        return self

    def delete(self, commit: bool = True):
        """Remove the record from the database."""
        if self:
            db.session.delete(self)
        if commit:
            try:
                db.session.commit()
            except SQLAlchemyError as e:
                logger.error(f'对象{self}删除数据出错 ERROR:{str(e)}')

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
                # 结果转换为dict,ref: https://stackoverflow.com/a/1960546/14295718
                try:
                    inst_dict = {col.name: getattr(inst, col.name) for col in cls.__table__.columns}
                except AttributeError:
                    '''
                    When the sqlalchemy ORM class attributes are different from database columns, ref:
                    https://stackoverflow.com/a/27948279/14295718
                    当设计数据库的ORM时，如果我们的类属性和数据库的列名不同时，如何获取类的属性
                    '''
                    inst_dict = {col[0]: getattr(inst, col[0]) for col in inspect(cls).column_attrs.items()}

                if not utils.is_sub_dict(kwargs, inst_dict):
                    inst.update(kwargs)
                    db.session.commit()
                    if do_log_flag:
                        logger.success(f'The instance: {inst} has been UPDATED successful.')
                else:
                    if do_log_flag:
                        logger.info(f'The instance: {inst} do not need update because it is sub dict of {kwargs}.')
            else:
                raise UniqueInstanceError(f'The query result:{result} get the count of instance more than 1.')

        else:
            inst = cls.create(**kwargs)
            if do_log_flag:
                logger.success(f'The {inst} has been CREATED successful.')
        return inst


class Model(CRUDMixin, db.Model):
    """Base model class that includes CRUD convenience methods."""
    # ref: [How do I declare a base model class in Flask-SQLAlchemy? - Stack Overflow]
    # (https://stackoverflow.com/questions/22976445/how-do-i-declare-a-base-model-class-in-flask-sqlalchemy)
    __abstract__ = True

    # def to_dict(self):
    #     columns = self.__table__.columns.keys()
    #     return {key: getattr(self, key) for key in columns}


class PkModel(Model):
    """Base model class that includes CRUD convenience methods, plus adds a 'primary key' column named ``id``."""

    __abstract__ = True
    id = Column(db.Integer, primary_key=True)

    @classmethod
    def table_name(cls):
        """
        返回表名称
        :return:
        """
        return cls.__table__.name

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
    created_at = Column(db.DateTime(timezone=True), default=datetime.now, server_default=func.now(), comment='创建时间')


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
    if max_identifier != (None,):
        max_num = max_identifier[0]
        if max_num is not None:
            increase_int = random.randrange(1, 3)
            fp_identifier = int(max_num) + increase_int
            return f'{fp_identifier:0{min_len}}'
    return fp_identifier

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/2/13 17:50
"""
角色和用户之间互为多对多关系（ bidirectional relationship）
[多对多双向关系](https://docs.sqlalchemy.org/en/14/orm/basic_relationships.html#many-to-many)
"""
from __future__ import annotations

import datetime
import hashlib
from typing import Union

from flask import current_app
from flask_praetorian.exceptions import AuthenticationError

from sqlalchemy import DDL, Table, event, or_

from backend.fundmate import settings
from backend.fundmate.database import Column, CreateDateModel, PkModel, db, relationship
from backend.fundmate.extensions import guard


user_role_table = Table('user_role', db.Model.metadata, Column('user_id', db.Integer, db.ForeignKey('users.id')),
                        Column('role_id', db.Integer, db.ForeignKey('roles.id')),
                        db.PrimaryKeyConstraint('user_id', 'role_id'))


class Role(PkModel):
    """角色表"""

    __tablename__ = "roles"

    name = Column(db.String(80), unique=True, nullable=False)
    user = relationship("User", secondary=user_role_table, back_populates="role")

    def __init__(self, name, **kwargs):
        """Create instance."""
        super().__init__(name=name, **kwargs)

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<Role({self.name})>"


class User(PkModel, CreateDateModel):
    """用户管理表
    """

    __tablename__ = 'users'
    __table_args__ = {'comment': '用户表'}
    # TODO: 用户起始id从1000开始
    id = Column(db.Integer().with_variant(db.Integer, "sqlite"), primary_key=True)
    name = Column(db.String(16), comment='用户名')
    username = Column(db.String(16), unique=True, nullable=False, comment='登录用户名')
    password = Column(db.String(150), nullable=False, comment='用户密码')
    email = Column(db.String(30), unique=True, nullable=False, comment='注册邮箱')
    phone_num = Column(db.String(11), comment='注册手机号')
    custom_avatar = Column(db.String(512), comment='用户自定义头像')
    is_confirmed = Column(db.Boolean(), default=False, comment='注册确认')
    is_admin = Column(db.Boolean(), default=False)  # TODO: is this necessary?
    is_vip = Column(db.Boolean(), default=False)
    profile = Column(db.TEXT)
    is_active = db.Column(db.Boolean(), default=True, comment='是否激活可用，置为False可以禁用用户')
    # TODO: 是否有必要，修改为modified？
    last_login = Column(db.TIMESTAMP, nullable=False, server_default=db.func.now(), onupdate=datetime.datetime.now)
    role = relationship("Role", secondary=user_role_table, back_populates="user")

    def __init__(self, **kwargs) -> None:
        """Create instance."""
        super().__init__(**kwargs)
        password = kwargs.get('password')
        if password:
            self.password = self.set_password(password)

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<User({self.username!r})>"

    @staticmethod
    def set_password(password: str) -> str:
        """Set password."""
        return guard.hash_password(password)

    def check_password(self, password: str) -> bool:
        """Check password."""
        try:
            return guard.authenticate(self.username, password) is not None
        except AuthenticationError:
            return False

    @property
    def avatar(self) -> Column | str:
        """Load custom avatar or get the gravatar image"""
        if self.custom_avatar:
            return self.custom_avatar
        email_hash = hashlib.md5((self.email or self.name).strip().lower().encode()).hexdigest()
        return f'https://www.gravatar.com/avatar/{email_hash}?d=monsterid'

    @classmethod
    def get_admin(cls):
        """Get the admin user. The only one will be returned."""
        rv: Union[None, User] = cls.query.filter_by(is_admin=True).first()
        if not rv:
            admin_info = {
                'name': 'admin',
                'email': current_app.config["ADMIN_EMAIL"] or settings.INFO_MAIL_ADDR,
                'password': current_app.config["DEFAULT_ADMIN_PASSWORD"],
                'is_admin': True,
                'is_vip': True,
                'profile': 'With great power comes great responsibility.'
            }
            rv = cls.create(**admin_info)
        return rv

    @property
    def identity(self):
        """
        *Required Attribute or Property*

        flask-praetorian requires that the user class has an ``identity`` instance
        attribute or property that provides the unique id of the user instance
        """
        return self.id

    @property
    def rolenames(self):
        """
        *Required Attribute or Property*

        flask-praetorian requires that the user class has a ``rolenames`` instance
        attribute or property that provides a list of strings that describe the roles
        attached to the user instance
        """
        return [item.name for item in self.role]

    @classmethod
    def lookup(cls, user_unique: str):
        """
        *Required Method*

        flask-praetorian requires that the user class implements a ``lookup()``
        class method that takes a single ``username`` or ``email`` argument and returns a user
        instance if there is one that matches or ``None`` if there is not.
        """
        return cls.query.filter(or_(cls.username == user_unique, cls.email == user_unique)).one_or_none()

    @classmethod
    def identify(cls, id):
        """
        *Required Method*

        flask-praetorian requires that the user class implements an ``identify()``
        class method that takes a single ``id`` argument and returns user instance if
        there is one that matches or ``None`` if there is not.
        """
        return cls.query.get(id)

    def is_valid(self):
        return self.is_active


"""
参考链接：[python - Setting SQLAlchemy autoincrement start value - Stack Overflow](https://stackoverflow.com/a/10500177)
一种不太优雅的方式：
```python
from sqlalchemy import event
from sqlalchemy import DDL
event.listen(
    Article.__table__,
    "after_create",
    DDL("ALTER TABLE %(table)s AUTO_INCREMENT = 1001;")
)
```
根据：[Set start value for AUTOINCREMENT in SQLite - Stack Overflow](
https://stackoverflow.com/questions/692856/set-start-value-for-autoincrement-in-sqlite)，
对于sqlite，应该是不支持直接配置的，只能手动添加并删除;
> SQLite keeps track of the largest ROWID that a table has ever held using the special SQLITE_SEQUENCE table.
The SQLITE_SEQUENCE table is created and initialized automatically whenever a normal table that contains an
AUTOINCREMENT column is created. The content of the SQLITE_SEQUENCE table can be modified using ordinary UPDATE, INSERT,
 and DELETE statements. But making modifications to this table will likely perturb the AUTOINCREMENT key generation
 algorithm. Make sure you know what you are doing before you undertake such changes.

```
UPDATE SQLITE_SEQUENCE SET seq = <n> WHERE name = '<table>'
```
https://stackoverflow.com/a/26332544
```
BEGIN TRANSACTION;

UPDATE sqlite_sequence SET seq = <n> WHERE name = '<table>';

INSERT INTO sqlite_sequence (name,seq) SELECT '<table>', <n> WHERE NOT EXISTS
           (SELECT changes() AS change FROM sqlite_sequence WHERE change <> 0);
COMMIT;
```

根据https://stackoverflow.com/a/10495449，对于PostgreSQL ，可以使用
```python
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import Sequence

Base = declarative_base()

class Article(Base):
    __tablename__ = 'article'
    aid = Column(INTEGER(unsigned=True, zerofill=True),
                 Sequence('article_aid_seq', start=1001, increment=1),
                 primary_key=True)
```
 """
event.listen(User.__table__, "after_create",
             DDL("ALTER TABLE %(table)s AUTO_INCREMENT = 1001;").execute_if(dialect=('postgresql', 'mysql')))

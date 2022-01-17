# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
from typing import Union

from flask import current_app

from itsdangerous import BadSignature, SignatureExpired
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from sqlalchemy import DDL, Table, event, or_
from werkzeug.security import check_password_hash

from backend.fundmate import settings
from backend.fundmate.database import Base, Column, CreateDateModel, PkModel, db, relationship
from backend.fundmate.extensions import guard

# [多对多双向关系](https://docs.sqlalchemy.org/en/14/orm/basic_relationships.html#many-to-many)
'''
角色和用户之间互为多对多关系（ bidirectional relationship）
'''
# [多对多双向关系](https://docs.sqlalchemy.org/en/14/orm/basic_relationships.html#many-to-many)
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
    TODO: 用户起始id从1000开始
    """

    __tablename__ = 'users'
    __table_args__ = {'comment': '用户表'}

    name = Column(db.String(16), comment='用户名')
    username = Column(db.String(16), unique=True, nullable=False, comment='登录用户名')
    password = Column(db.String(150), nullable=False, comment='用户密码')
    email = Column(db.String(30), unique=True, nullable=False, comment='注册邮箱')
    phone_num = Column(db.String(11), comment='注册手机号')
    custom_avatar = Column(db.String(512), comment='用户自定义头像')
    is_confirmed = Column(db.Boolean(), default=False, comment='注册确认')
    is_admin = Column(db.Boolean(), default=False)
    is_vip = Column(db.Boolean(), default=False)
    profile = Column(db.TEXT)
    is_active = db.Column(db.Boolean(), default=True, comment='是否激活可用，置为False可以禁用用户')
    # TODO: 是否有必要，修改为modified？
    last_login = Column(db.TIMESTAMP,
                        nullable=False,
                        server_default=db.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))
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
        return check_password_hash(self.password, password)

    @property
    def avatar(self) -> str:
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

    @classmethod
    def verify_auth_token(cls, token: str):
        s = Serializer(current_app.config["SECRET_KEY"])
        try:
            data = s.loads(token)
        except (BadSignature, SignatureExpired):
            return None
        user = cls.get_by_id(data["id"])
        return user

    def generate_token(self, expiration: int = 24 * 60 * 60):
        s = Serializer(current_app.config["SECRET_KEY"], expires_in=expiration)
        return s.dumps({"id": self.id})

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


# 自增id起始值
event.listen(User.__table__, "after_create", DDL("ALTER TABLE %(table)s AUTO_INCREMENT = 1001;"))

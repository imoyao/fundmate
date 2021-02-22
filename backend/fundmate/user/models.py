# -*- coding: utf-8 -*-
"""User models."""
import hashlib
from typing import Union

from flask import current_app
from flask_login import AnonymousUserMixin, UserMixin
from itsdangerous import BadSignature, SignatureExpired
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from werkzeug.security import check_password_hash, generate_password_hash

from backend.fundmate.database import Column, CreateDateModel, PkModel, db, reference_col, relationship
from backend.fundmate.extensions import login_manager


class Role(PkModel):
    """A role for a user."""

    __tablename__ = "roles"
    name = Column(db.String(80), unique=True, nullable=False)
    user_id = reference_col("users", nullable=True)
    user = relationship("User", backref="roles")    # TODO:推荐使用 back_populates

    def __init__(self, name, **kwargs):
        """Create instance."""
        super().__init__(name=name, **kwargs)

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<Role({self.name})>"


class User(PkModel, CreateDateModel, UserMixin):
    """A user of the app."""

    __tablename__ = 'users'
    __table_args__ = {'comment': '用户表'}
    name = Column(db.String(16), comment='用户名')
    username = Column(db.String(16), unique=True, nullable=False, comment='登录用户名')
    password = Column(db.String(40), nullable=False, comment='用户密码')
    email = Column(db.String(30), unique=True, nullable=False, comment='注册邮箱')
    phone_num = Column(db.String(11), comment='注册手机号')
    custom_avatar = Column(db.String(512), comment='用户自定义头像')
    is_confirmed = Column(db.Boolean(), default=False, comment='注册确认')
    is_admin = Column(db.Boolean(), default=False)
    is_vip = Column(db.Boolean(), default=False)
    profile = Column(db.TEXT)
    last_login = Column(
        db.TIMESTAMP,
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))

    def __init__(self, username, email, password=None, **kwargs) -> None:
        """Create instance."""
        super().__init__(username=username, email=email, **kwargs)
        if password:
            self.password = self.set_password(password)
        else:
            self.password = None

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<User({self.username!r})>"

    @staticmethod
    def set_password(password: str) -> str:
        """Set password."""
        return generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check password."""
        return check_password_hash(self.password, password)

    @property
    def avatar(self) -> str:
        """Load custom avatar or get the gravatar image"""
        if self.custom_avatar:
            return self.custom_avatar
        email_hash = hashlib.md5(
            (self.email or self.name).strip().lower().encode()).hexdigest()
        return f'https://www.gravatar.com/avatar/{email_hash}?d=monsterid'

    @classmethod
    def get_admin(cls):
        """Get the admin user. The only one will be returned."""
        rv: Union[None, User] = cls.query.filter_by(is_admin=True).first()
        if not rv:
            admin_info = {
                'name': 'admin',
                'email': current_app.config["ADMIN_EMAIL"]
                or 'fundmate@163.com',
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


class Guest(AnonymousUserMixin):
    @property
    def is_admin(self):
        return False


login_manager.anonymous_user = Guest

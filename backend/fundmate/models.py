# coding: utf-8
import hashlib
from datetime import datetime
from typing import Union

from flask import current_app
from flask_login import UserMixin, AnonymousUserMixin

from itsdangerous import BadSignature, SignatureExpired
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from sqlalchemy import TIMESTAMP, Date, DateTime, Float, String, text
from sqlalchemy.dialects.mysql import INTEGER, TINYINT, TINYTEXT
from werkzeug.security import check_password_hash, generate_password_hash

from backend.fundmate.database import Column, PkModel

from .extensions import db, login_manager


class Account(PkModel):
    __tablename__ = 'account'
    __table_args__ = {'comment': '账本（钱包）'}

    name = Column(String(255), comment='账本名称')
    create_date = Column(DateTime, default=datetime.utcnow, comment='账本创建时间')
    creator_id = Column(INTEGER(11), comment='管理人（群主）')
    comment = Column(String(255), comment='账本备注')


class AccountFund(PkModel):
    __tablename__ = 'account-fund'

    fund_id = Column(INTEGER(11), comment='基金编号')
    account_id = Column(INTEGER(11), comment='账本编号')


class CashFlow(PkModel):
    __tablename__ = 'cashflow'

    uid = Column(INTEGER(11), comment='购买用户')
    fid = Column(INTEGER(11), comment='所购买的基金')
    amount = Column(INTEGER(10), comment='购买金额')
    date = Column(TIMESTAMP,
                  nullable=False,
                  server_default=text("CURRENT_TIMESTAMP"),
                  comment='购买日期（确认日期）')
    comment = Column(String(30), comment='复盘备注')


class DailyWorth(PkModel):
    __tablename__ = 'dailyworth'

    fid = Column(INTEGER(11), comment='基金编号')
    price = Column(Float, comment='基金单日净值')
    date = Column(Date, comment='日期')


class Fund(PkModel):
    __tablename__ = 'fund'

    name = Column(String(30), comment='基金名称')
    fund_code = Column(INTEGER(11), unique=True)
    type = Column(TINYINT(4), comment='基金类型')
    co_id = Column(TINYINT(4), comment='所属基金公司')


class FundRate(PkModel):
    __tablename__ = 'fund-rate'

    fid = Column(INTEGER(11), comment='基金编号')
    rule_id = Column(INTEGER(11), comment='费率编号')
    rate = Column(INTEGER(10), comment='费率百分比')
    type = Column(TINYINT(1), comment='卖出和买入')


class FundMgr(PkModel):
    """relation between Fund and Mgr
    """
    __tablename__ = 'fund-mgr'
    __table_args__ = {'comment': '基金与经理关联表'}

    fid = Column(INTEGER(11), comment='基金编号')
    mgr_id = Column(INTEGER(11), comment='基金经理编号')
    start_date = Column(DateTime)
    end_date = Column(DateTime)


class FundCompany(PkModel):
    """relation between Fund and Company
    """
    __tablename__ = 'fundcompany'

    name = Column(String(30))
    co_id = Column(String(10), comment='基金公司编号')


class FundType(PkModel):
    __tablename__ = 'fundtype'
    __table_args__ = {'comment': '基金小类表'}

    name = Column(String(255))
    var_id = Column(INTEGER(11))


class FundVariety(PkModel):
    __tablename__ = 'fundvariety'
    __table_args__ = {'comment': '基金大类表'}

    name = Column(String(255))


class HandPick(PkModel):
    __tablename__ = 'handpick'
    __table_args__ = {'comment': '自选基金'}

    uid = Column(INTEGER(11), comment='用户编号')
    fid = Column(INTEGER(11), comment='基金编号')
    pick_time = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment='收藏时间')
    comment = Column(String(30), comment='备注')


class InRule(PkModel):
    __tablename__ = 'inrule'

    start_quota = Column(TINYINT(4), comment='计费开始额度')
    end_quota = Column(TINYINT(4), comment='计费结束额度')


class Mgr(PkModel):
    __tablename__ = 'mgr'
    __table_args__ = {'comment': '基金经理'}

    mgr_id = Column(INTEGER(10), comment='经理编号')
    name = Column(String(4), comment='经理名称')
    company_id = Column(INTEGER(10), comment='所属公司ID')


class OutRule(PkModel):
    __tablename__ = 'outrule'
    __table_args__ = {'comment': '赎回规则'}

    start_day = Column(TINYINT(4), comment='计费开始天数')
    end_day = Column(TINYINT(4), comment='计费结束天数')


class User(PkModel, UserMixin):
    __tablename__ = 'user'
    __table_args__ = {'comment': '用户表'}
    name = Column(String(16), comment='用户名')
    password = Column(String(40), nullable=False, comment='用户密码')
    email = Column(String(30), comment='注册邮箱')
    phone_num = Column(String(11), comment='注册手机号')
    custom_avatar = Column(String(512), comment='用户自定义头像')
    create_time = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment='注册时间')
    is_confirmed = Column(db.Boolean, default=False, comment='注册确认')
    is_admin = Column(db.Boolean(), default=False)
    is_vip = Column(db.Boolean(), default=False)
    profile = Column(TINYTEXT)
    last_login = Column(TIMESTAMP)

    def __init__(self, **kwargs) -> None:
        password = kwargs.pop("password", None)
        if password:
            password = self.set_password(password)
            kwargs["password"] = password
        super().__init__(**kwargs)

    @staticmethod
    def set_password(password: str) -> str:
        return generate_password_hash(password)

    def verify_password(self, password: str) -> bool:
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

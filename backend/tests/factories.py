# -*- coding: utf-8 -*-
"""Factories to help in tests."""
import logging

from factory import Faker, LazyAttribute, PostGenerationMethodCall
from factory.alchemy import SQLAlchemyModelFactory

from faker import Factory

from backend.fundmate.database import db
from backend.fundmate.fund.models import Fund
from backend.fundmate.user.models import Role, User


fake = Factory().create('zh_CN')

logger = logging.getLogger('faker')
logger.setLevel(logging.ERROR)


class BaseFactory(SQLAlchemyModelFactory):
    """Base factory."""

    class Meta:
        """Factory configuration."""

        abstract = True
        sqlalchemy_session = db.session


class UserFactory(BaseFactory):
    """User factory."""

    username = Faker("name", locale="zh_CN")
    email = Faker("email")
    password = PostGenerationMethodCall("set_password", 'example', )  # ！！！注意此处逗号
    is_active = True
    is_confirmed = True

    class Meta:
        """Factory configuration."""

        model = User


class RoleFactory(BaseFactory):
    """Role factory."""

    name = Faker('name')

    class Meta:
        """Factory configuration."""

        model = Role


class FundFactory(BaseFactory):
    """Fund factory."""
    fund_code = LazyAttribute(lambda obj: str(obj.fund_code_num))
    name = Faker('word', locale="zh_CN")
    full_name = LazyAttribute(lambda obj: f'{obj.company}{obj.fund_kw}基金')

    class Meta:
        """Factory configuration."""

        model = Fund

    class Params:
        """
        有的参数
        """
        fund_code_num = Faker("random_number", digits=6, fix_len=True)
        company = Faker('word', locale="zh_CN", ext_word_list=['易方达', '工银瑞信', '富国', '交银'])
        fund_kw = Faker('word', locale="zh_CN",
                        ext_word_list=['成长', '质量', '持续成长', '低波', '消费', '医疗', '科技', '价值', '精选',
                                       '优选',
                                       '红利',
                                       '稳健', '主题'])

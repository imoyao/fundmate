# -*- coding: utf-8 -*-
"""Factories to help in tests."""
import logging

from factory import Faker, PostGenerationMethodCall
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
    fund_code = Faker("random_number", digits=6, fix_len=True)
    name = Faker('name', locale="zh_CN")
    full_name = Faker('text', locale="zh_CN", max_nb_chars=20)

    class Meta:
        """Factory configuration."""

        model = Fund

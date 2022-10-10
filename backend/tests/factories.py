# -*- coding: utf-8 -*-
"""Factories to help in tests."""
from factory import Faker, PostGenerationMethodCall
from factory.alchemy import SQLAlchemyModelFactory

from backend.fundmate.database import db
from backend.fundmate.user.models import User


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

    class Meta:
        """Factory configuration."""

        model = User

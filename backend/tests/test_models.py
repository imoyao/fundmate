# -*- coding: utf-8 -*-
"""Model unit tests."""
import datetime as dt

import pytest
from faker import Faker

from backend.fundmate.user.models import Role, User

from ..fundmate import settings
from .factories import UserFactory


@pytest.fixture()
def user_instance():
    user = User.create(username=Faker('zh-cn').name(), email=Faker().email(), password=Faker().password())
    return user


@pytest.mark.usefixtures("db")
class TestUser:
    """User tests."""

    def test_factory(self):
        """Test user factory."""
        user = UserFactory()
        assert bool(user.username)
        assert bool(user.email)
        assert not user.created_at
        assert not user.is_admin
        assert user.is_active
        assert user.is_confirmed

    @pytest.mark.create_user
    def test_get_by_id(self, user_instance):
        """Get user by ID."""
        retrieved = User.get_by_id(user_instance.id)
        assert retrieved == user_instance

    @pytest.mark.create_user
    def test_created_at_defaults_to_datetime(self, user_instance):
        """Test creation date."""
        assert bool(user_instance.created_at)
        assert isinstance(user_instance.created_at, dt.datetime)

    def test_factory_check_password(self):
        """Check password."""
        fake = Faker()
        pwd = fake.password()
        user = UserFactory(password=pwd)
        assert user.check_password(pwd) is True
        assert user.check_password("i_am_hacker") is False

    def test_roles(self):
        """Add a role to a user."""
        role = Role.create(name=settings.ADMIN_ROLE_NAME)
        user = UserFactory(is_admin=True)
        user.roles.append(role)
        user.save()
        assert role in user.roles

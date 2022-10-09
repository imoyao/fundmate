# -*- coding: utf-8 -*-
"""Model unit tests."""
import datetime as dt

import pytest

from backend.fundmate.user.models import Role, User

from .factories import UserFactory


@pytest.fixture
def the_test_user_info():
    """
    复用用户信息
    :return:
    """
    return {
        "username": "foo",
        "email": "foo@bar.com",
        "password": "baz123456",
    }


@pytest.mark.usefixtures("db")
class TestUser:
    """User tests."""

    def test_get_by_id(self, the_test_user_info):
        """Get user by ID."""
        user = User.create(username=the_test_user_info.get('username'),
                           email=the_test_user_info.get('email'),
                           password=the_test_user_info.get('password'))
        retrieved = User.get_by_id(user.id)
        assert retrieved == user

    def test_created_at_defaults_to_datetime(self, the_test_user_info):
        """Test creation date."""
        user = User.create(username=the_test_user_info.get('username'),
                           email=the_test_user_info.get('email'),
                           password=the_test_user_info.get('password'))
        assert bool(user.created_at)
        assert isinstance(user.created_at, dt.datetime)

    def test_factory(self, db):
        """Test user factory."""
        user = UserFactory(password="myprecious")
        db.session.commit()
        assert bool(user.username)
        assert bool(user.email)
        assert bool(user.created_at)
        assert user.is_admin is False
        assert user.is_active is True
        assert user.check_password("myprecious")

    def test_check_password(self, the_test_user_info):
        """Check password."""
        user = User.create(username=the_test_user_info.get('username'),
                           email=the_test_user_info.get('email'),
                           password=the_test_user_info.get('password'))
        pwd = the_test_user_info.get('password')
        assert user.check_password(pwd) is True
        assert user.check_password("i_am_hacker") is False

    def test_roles(self):
        """Add a role to a user."""
        role = Role.create(name="admin")
        user = UserFactory()
        user.role.append(role)
        user.save()
        assert role in user.role

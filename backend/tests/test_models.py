# -*- coding: utf-8 -*-
"""Model unit tests."""
import datetime as dt

import pytest

from backend.fundmate.user.models import Role, User

from .factories import UserFactory


the_test_user_info = {
    "username": "foo",
    "email": "foo@bar.com",
    "password": "baz123456",
}


@pytest.mark.usefixtures("db")
class TestUser:
    """User tests."""

    def test_get_by_id(self):
        """Get user by ID."""
        user = User.create(username=the_test_user_info.get('username'),
                           email=the_test_user_info.get('email'),
                           password=the_test_user_info.get('password'))
        retrieved = User.get_by_id(user.id)
        assert retrieved == user

    def test_created_at_defaults_to_datetime(self):
        """Test creation date."""
        user = User.create(username=the_test_user_info.get('username'),
                           email=the_test_user_info.get('email'),
                           password=the_test_user_info.get('password'))
        assert bool(user.created_at)
        assert isinstance(user.created_at, dt.datetime)

    def test_factory(self, db):
        """Test user factory."""
        # FIXME: 如何使用？
        # user = UserFactory(password="myprecious")
        user = User.create(username=the_test_user_info.get('username'),
                           email=the_test_user_info.get('email'),
                           password=the_test_user_info.get('password'))
        assert bool(user.username)
        assert bool(user.email)
        assert user.created_at
        assert not user.is_admin
        assert user.is_active

    def test_check_password(self):
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
        user = UserFactory(is_admin=True)
        user.roles.append(role)
        user.save()
        assert role in user.roles

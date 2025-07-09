# -*- coding: utf-8 -*-
import datetime as dt

import pytest
from faker import Faker

from backend.fundmate import settings
from backend.fundmate.extensions import guard
from backend.fundmate.user.models import Role, User
from backend.tests.factories import RoleFactory, UserFactory


class TestRole:

    def test_role(self):
        user = UserFactory()
        role = RoleFactory()
        role_name = role.name
        assert role_name
        assert str(role) == f'<Role({role_name})>'
        user.roles.append(role)
        user.save()
        assert role in user.roles


def delete_user(user_inst):
    """验证完成删除用户"""
    user_inst.delete()
    return 0


@pytest.fixture()
def user_instance():
    user = User.create(username=Faker('zh-cn').name(), email=Faker().email(), password=Faker().password())
    return user


class TestUser:

    def test_factory(self):
        """Test user factory."""
        user = UserFactory()
        assert bool(user.username)
        assert bool(user.email)
        assert not user.created_at
        assert not user.is_admin
        assert user.is_active
        assert user.is_confirmed

    def test_get_by_id(self, user_instance):
        """Get user by ID."""
        retrieved = User.get_by_id(user_instance.id)
        assert retrieved == user_instance

    def test_created_at_defaults_to_datetime(self, user_instance):
        """Test creation date."""
        # user_instance = UserFactory()
        assert bool(user_instance.created_at)
        assert isinstance(user_instance.created_at, dt.datetime)
        # request.addfinalizer(lambda: delete_user(user_instance))

    def test_factory_check_password(self, request):
        """Check password."""
        fake = Faker()
        pwd = fake.password()
        user = UserFactory(password=pwd)
        assert user.check_password(pwd) is True
        assert user.check_password("i_am_hacker") is False
        request.addfinalizer(lambda: delete_user(user))

    def test_roles(self, request):
        """Add a role to a user."""
        role = Role.create(name=settings.ADMIN_ROLE_NAME)
        user = UserFactory(is_admin=True)
        user.roles.append(role)
        user.save()
        assert role in user.roles
        request.addfinalizer(lambda: delete_user(user))
        request.addfinalizer(lambda: delete_user(role))

    def test_set_password(self, app):
        pw = Faker().password()
        hash_pw = User().set_password(pw)
        assert guard.pwd_ctx.identify(hash_pw) == "pbkdf2_sha512"

    def test_lookup(self, app):
        with app.app_context():
            user = User.lookup(app.config.get('TEST_EMAIL'))
            assert user

    def test_check_password(self, app):
        with app.app_context():
            user = User.lookup(app.config.get('TEST_EMAIL'))
            is_right = user.check_password(password=app.config.get('TEST_PASSWORD'))
            is_not_right = user.check_password(password=Faker().password())
            assert is_right
            assert not is_not_right

    def test_avatar(self, app, request):
        with app.app_context():
            user = UserFactory()
            assert user.avatar
            assert not user.custom_avatar
            foo_avatar = 'https://pic1.zhimg.com/v2-abed1a8c04700ba7d72b45195223e0ff_l.jpeg'
            user.update(custom_avatar=foo_avatar)
            assert user.custom_avatar == foo_avatar
            request.addfinalizer(lambda: delete_user(user))

    def test_get_admin(self, app):
        with app.app_context():
            user = User.lookup(app.config.get('TEST_EMAIL'))
            assert not user.is_admin
            User().set_admin(app.config.get('TEST_EMAIL'))
            assert user.is_admin
            assert User().get_admin()

    def test_identity(self, app):
        with app.app_context():
            user = User.lookup(app.config.get('TEST_EMAIL'))
            _identity = user.identity
            assert _identity == user.id

    def test_rolenames(self, app, request):
        with app.app_context():
            user = User.lookup(app.config.get('TEST_EMAIL'))
            role_name = app.config.get('TEST_ROLE_NAME')
            role = Role.create(name=role_name, user=[user])
            user.roles.append(role)
            user.save()
            roles = user.rolenames
            assert role_name in roles
            request.addfinalizer(lambda: delete_user(role))

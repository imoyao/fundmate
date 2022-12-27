# -*- coding: utf-8 -*-
from faker import Faker

from backend.fundmate.extensions import guard
from backend.fundmate.user.models import Role, User


class TestUser:

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

    def test_avatar(self, app):
        with app.app_context():
            user = User.lookup(app.config.get('TEST_EMAIL'))
            assert user.avatar

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

    def test_rolenames(self, app):
        with app.app_context():
            user = User.lookup(app.config.get('TEST_EMAIL'))
            role_name = app.config.get('TEST_ROLE_NAME')
            role = Role.create(name=role_name, user=[user])
            user.roles.append(role)
            user.save()
            roles = user.rolenames
            assert role_name in roles

# -*- coding: utf-8 -*-
"""Defines fixtures available to all tests.
该文件的作用域是它同级的文件或者文件夹，以及同级文件夹里面的文件或者目录；
如果放到某个package下，那就在该package内及其下的目录有效。
参考：
https://github.com/d2verb/battery/blob/05571f6aa809af64b8e3d45483cebfe15779d48d/tests/conftest.py
https://github.com/pallets/flask/blob/2.0.2/examples/tutorial/tests/conftest.py
"""
import os

import pytest
from environs import Env as EnvParser

from backend.fundmate.app import create_app
from backend.fundmate.database import db as _db

from .factories import UserFactory

env = EnvParser()
env.read_env()


@pytest.fixture(scope='session')
def app():
    """An application for the tests."""
    # 默认加载基础配置
    _app = create_app()
    # _app.logger.setLevel(logging.CRITICAL)

    ctx = _app.test_request_context()
    ctx.push()

    yield _app

    ctx.pop()


@pytest.fixture(scope='session')
def client(app, request):
    """
    直接使用test_client方法获取测试专用的客户端
    :param request:
    :param app:
    :return:
    """

    def teardown():
        """
        在项目结束时恢复配置
        :return:
        """
        app.config['TESTING'] = False
        app.config['FLASK_ENV'] = origin_flask_env

    # 读取初始FLASK_ENV配置
    origin_flask_env = env.str('FLASK_ENV', default='default')
    print(origin_flask_env)
    # 加载测试环境的配置
    app.config['TESTING'] = True
    app.config['FLASK_ENV'] = 'testing'
    # 执行回收函数
    request.addfinalizer(teardown)
    return app.test_client()


@pytest.fixture(scope='session')
def db(app):
    """Create database for the tests.
    数据库创建
    """
    _db.app = app
    with app.app_context():
        _db.create_all()

    yield _db

    # Explicitly close DB connection
    _db.session.close()
    _db.drop_all()


@pytest.fixture(scope='session')
def user(db):
    """Create user for the tests."""
    # TODO: 用户密码可以放到配置文件中
    user = UserFactory(password='test123456')
    db.session.commit()
    return user


# @pytest.fixture
# def test_app_view(app):
#     """Create Webtest app.
#     图形化界面测试，目前可能用不到
#     """
#     return TestApp(app)


@pytest.fixture(scope='session')
def cli_runner(app):
    return app.test_cli_runner()


@pytest.fixture
def test_apps(monkeypatch):
    path = os.path.abspath(os.path.join(os.path.dirname(__file__)))
    print(path)
    monkeypatch.syspath_prepend(os.path.abspath(os.path.join(os.path.dirname(__file__), 'tests')))

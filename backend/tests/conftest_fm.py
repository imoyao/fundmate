# -*- coding: utf-8 -*-
"""Defines fixtures available to all tests.
该文件的作用域是它同级的文件或者文件夹，以及同级文件夹里面的文件或者目录；
如果放到某个package下，那就在该package内及其下的目录有效。
参考：
1. https://github.com/d2verb/battery/blob/05571f6aa809af64b8e3d45483cebfe15779d48d/tests/conftest.py
2. https://github.com/pallets/flask/blob/2.0.2/examples/tutorial/tests/conftest.py
3. https://github.com/dusktreader/flask-praetorian/blob/master/tests/conftest.py
"""

import os
import sqlite3

import pytest
from click.testing import CliRunner
from environs import Env as EnvParser
from flask import current_app, g
from flask_mail import Mail
from flask_praetorian import Praetorian

from backend.fundmate.app import create_app

# from backend.fundmate.commands import init_db
from backend.fundmate.database import db as _db

from ..fundmate.user.models import User
from .factories import UserFactory

# import tempfile

env = EnvParser()
env.read_env()

# SQL_DATA = prepare_data()
_guard = Praetorian()
_mail = Mail()


def get_db():
    """Connect to the application's configured database. The connection
    is unique for each request and will be reused if this is called
    again.
    """
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'], detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row

    return g.db


@pytest.fixture(scope='session')
def runner(request):
    return CliRunner()


def read_sql(sql_name=''):
    with open(os.path.join(os.path.dirname(__file__), 'db_data', sql_name), 'rb') as f:
        _data_sql = f.read().decode('utf8')
    return _data_sql


def initial_table():
    """Clear existing data and create new tables."""
    db = get_db()
    schema_sql = read_sql('fmp_schema_sqlite.sql')
    # print(schema_sql)
    db.executescript(schema_sql)


@pytest.fixture(scope='session')
def app(runner):
    """An application for the tests."""
    # 默认加载基础配置
    app = create_app()
    app.config.from_object('backend.fundmate.config.TestingConfig')
    _guard.init_app(app, User)

    _mail.init_app(app)
    app.mail = _mail
    # _app.logger.setLevel(logging.CRITICAL)
    assert app.config['DEBUG']
    assert app.config['TESTING']
    # with app.app_context():
    #     initial_table()
    #     db_cursor = get_db()
    #     fv_sql = read_sql('fund_variety.sql')
    #     db_cursor.executescript(fv_sql)
    #     """
    #     参阅：
    #     [Testing Click Applications — Click Documentation (8.1.x)]
    #     (https://click.palletsprojects.com/en/8.1.x/testing/)
    #     result = runner.invoke(init_db, ['--drop'])     # 传参 即True
    #     result = runner.invoke(init_db, [])         # 不传参 即False
    #     result = runner.invoke(init_db, ['--drop'], input='n') # 传参，不确认
    #     result = runner.invoke(init_db, ['--drop'], input='y') # 传参，确认
    #     """
    #     result = runner.invoke(init_db, [])
    #     # FIXME: 此处现在返回状态码为 1
    #     assert result.exit_code == 0
    #     # print(SQL_DATA,'----------')
    #     # get_db().executescript(SQL_DATA)

    yield app

    # close and remove the temporary database
    # FIXME:关闭+删除
    # os.close(db_fd)
    # os.unlink(db_path)


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

    # 读取初始FLASK_ENV配置，默认加载测试环境的配置
    origin_flask_env = env.str('FLASK_ENV', default='testing')
    # 执行回收函数
    request.addfinalizer(teardown)
    return app.test_client()


@pytest.fixture(scope='session')
def default_guard():
    """
    This fixture fetches the flask-praetorian instance to be used in testing
    """
    return _guard


@pytest.fixture(scope='session')
def mail():
    """
    This fixture simply fetches the db instance to be used in testing
    """
    return _mail


class AuthActions:
    """
    登录与退出
    """

    def __init__(self, app, client):
        self._client = client
        self._app = app

    def login(self, username=None, password=None):
        """
        FIXME: 调用生成token的接口
        :param username:
        :param password:
        :return:
        """
        if not username:
            username = self._app.config.get('TEST_USERNAME')
        if not password:
            password = self._app.config.get('TEST_PASSWORD')
        data = {'username': username, 'password': password}
        return self._client.post('users/login', json=data)

    def token(self, username=None, password=None):
        result = self.login(username, password)
        json_result = result.json
        return json_result.get('access_token')

    def logout(self):
        """
        调用退出登录的接口
        :return:
        """
        return self._client.get('/users/logout')


@pytest.fixture
def auth(app, client):
    return AuthActions(app, client)


@pytest.fixture
def bearer_header(auth):
    token = auth.token()
    _headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token}
    return _headers


@pytest.fixture(scope='session')
def db(app, request):
    """Create database for the tests.
    数据库创建
    """
    test_db_path = app.config.get('SQLITE_FILEPATH')
    if os.path.exists(test_db_path):
        os.unlink(test_db_path)

    def teardown():
        _db.session.remove()
        _db.drop_all()
        _db.session.commit()
        os.unlink(test_db_path)

    _db.app = app
    _db.create_all()

    request.addfinalizer(teardown)
    return _db


@pytest.fixture(scope='function')
def session(db, request):
    connection = db.engine.connect()
    transaction = connection.begin()

    options = dict(bind=connection, binds={})
    session = db.create_scoped_session(options=options)

    db.session = session

    def teardown():
        transaction.rollback()
        connection.close()
        session.remove()

    request.addfinalizer(teardown)
    return session


@pytest.fixture(scope='session', autouse=True)
def create_test_user(app, db):
    """Create user for the tests."""
    _test_mail = app.config.get('TEST_EMAIL')
    user = UserFactory(
        username=app.config.get('TEST_USERNAME'), email=_test_mail, password=app.config.get('TEST_PASSWORD')
    )
    yield user
    user = User.lookup(_test_mail)
    if user:
        user.delete()


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

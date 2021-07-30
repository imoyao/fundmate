#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/5/31 15:40
"""
测试API的模块
[Testing Flask Applications — Flask Documentation (2.1.x)](https://flask.palletsprojects.com/en/latest/testing/)
"""
import os
import tempfile

import pytest

from backend.autoapp import app
from backend.fundmate.commands import init_db


@pytest.fixture
def client():
    db_fd, app.config['DATABASE'] = tempfile.mkstemp()
    app.config['TESTING'] = True

    with app.test_client() as client:
        with app.app_context():
            init_db()
        yield client

    os.close(db_fd)
    os.unlink(app.config['DATABASE'])


def test_db():
    runner = app.test_cli_runner()

    # invoke the command directly
    result = runner.invoke(init_db, ['--drop'])
    assert 'Hello, Flask' in result.output


def test_empty_db(client):
    """Start with a blank database."""

    rv = client.get('/')
    assert b'No entries here so far' in rv.data


def test_index():
    with app.test_client() as c:
        rv = c.get('/')
        json_data = rv.get_json()
        assert json_data

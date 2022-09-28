# -*- coding: utf-8 -*-
"""
@Time ： 2022/9/28 18:08
@File ：test_db.py
@IDE ：PyCharm
"""
import sqlite3

import pytest

from backend.fundmate.commands import init_db


def test_get_close_db(app, db):
    with app.app_context():
        with pytest.raises(sqlite3.ProgrammingError) as e:
            db.execute("SELECT 1")

    assert "closed" in str(e.value)


def test_init_db_command(runner, monkeypatch):

    class Recorder:
        called = False

    def fake_init_db():
        Recorder.called = True

    # monkeypatch.setattr("backend.fundmate.database.db", fake_init_db)
    result = runner.invoke(init_db, [])
    print(result, '-----xxxx------------')
    assert "Initialized" in result.output
    assert Recorder.called

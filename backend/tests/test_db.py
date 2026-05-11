# -*- coding: utf-8 -*-
"""
@Time ： 2022/9/28 18:08
@File ：test_db.py
@IDE ：PyCharm
"""

from backend.fundmate.commands import init_db


def test_get_close_db(app, db):
    with app.app_context():
        print(db)
        db.execute('SELECT 1')
        # from sqlalchemy.sql import text
    #     result = db.select(text("1"))
    # with pytest.raises(sqlite3.ProgrammingError) as e:
    # result= db.select(text("SELECT 1"))

    # assert "closed" in str(e.value)


def test_init_db_command(runner, monkeypatch):
    # class Recorder:
    #     called = False

    # def fake_init_db():
    #     Recorder.called = True

    # TODO: 需要理解这段代码的含义
    # monkeypatch.setattr("backend.fundmate.database.db", fake_init_db)
    result = runner.invoke(init_db, [])
    assert result.exit_code == 0
    # assert "Result okay" in result.output
    # assert Recorder.called

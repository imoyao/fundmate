# -*- coding: utf-8 -*-
"""Extensions module. Each extension is initialized in the app factory located in base.py."""
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

from .exts.flask_loguru import Loguru


def tell_migrate_dont_detected_removed_table(object, name, type_, reflected,
                                             compare_to):
    """
    告诉migrate别删我已经存在的表：
    [python - Tell Flask-Migrate / Alembic to NOT drop any tables it doesn't know about - Stack Overflow](https://stackoverflow.com/questions/57631160/tell-flask-migrate-alembic-to-not-drop-any-tables-it-doesnt-know-about)

    [@migrate.configure not passing include_object to Alembic · Issue #323 · miguelgrinberg/Flask-Migrate](https://github.com/miguelgrinberg/Flask-Migrate/issues/323)
    :param object:
    :param name:
    :param type_:
    :param reflected:
    :param compare_to:
    :return:
    """
    if type_ == "table" and reflected and compare_to is None:
        return False
    else:
        return True


bcrypt = Bcrypt()
login_manager = LoginManager()
db = SQLAlchemy()
migrate = Migrate(include_object=tell_migrate_dont_detected_removed_table)
loguru = Loguru()

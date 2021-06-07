# -*- coding: utf-8 -*-
"""Helper utilities and decorators."""
from flask import flash
from datetime import datetime


def flash_errors(form, category="warning"):
    """Flash all errors for a form."""
    for field, errors in form.errors.items():
        for error in errors:
            flash(f"{getattr(form, field).label.text} - {error}", category)


def today() -> str:
    """
    a = datetime.today()
    datetime.datetime(2021, 6, 7, 17, 27, 13, 713125)
    a.strftime("%Y-%m-%d")
    '2021-06-07'
    :return:
    """
    return datetime.today().strftime("%Y-%m-%d")

# -*- coding: utf-8 -*-
"""Helper utilities and decorators.
date:https://kirby.kevinson.org/blog/iso-8601-the-better-date-format/

"""
from flask import flash
from datetime import datetime
import dateparser


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


def first_day_of_this_year():
    return datetime.today().replace(month=1, day=1).strftime("%Y-%m-%d")


def first_day_of_this_month():
    return dateparser.parse(str(datetime.today().month), settings={'PREFER_DAY_OF_MONTH': 'first'}).strftime("%Y-%m-%d")


if __name__ == '__main__':
    print(first_day_of_this_year(),first_day_of_this_month())

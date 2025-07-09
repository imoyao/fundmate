#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/5/31 15:40
"""
测试API的模块
[Testing Flask Applications — Flask Documentation (2.1.x)](https://flask.palletsprojects.com/en/latest/testing/)
"""

from backend.autoapp import app


def test_index():
    with app.test_client() as c:
        rv = c.get('/')
        assert rv
        assert rv.status_code == 200

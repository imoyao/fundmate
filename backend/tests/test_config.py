# -*- coding: utf-8 -*-
"""
@Time ： 2022/8/12 14:11
@File ：test_config.py
@IDE ：PyCharm
"""


def test_development_config(app):
    app.config.from_object('backend.fundmate.config.DevelopmentConfig')
    assert app.config['DEBUG']
    assert not app.config['TESTING']


def test_testing_config(app):
    app.config.from_object('backend.fundmate.config.TestingConfig')
    assert app.config['DEBUG']
    assert app.config['TESTING']


def test_production_config(app):
    app.config.from_object('backend.fundmate.config.ProductionConfig')
    assert not app.config['DEBUG']
    assert not app.config['TESTING']

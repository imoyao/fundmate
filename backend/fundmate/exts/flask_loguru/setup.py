#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/2/4 10:03
"""
Flask-SQLite3
-------------

This is the description for that library
"""
from setuptools import setup

setup(
    name='Flask-Loguru',
    version='1.0.0',
    url='https://masantu.com/flask-loguru/',
    license='BSD',
    author='imoyao',
    author_email='emailme8@163.com',
    description='Very short description',
    long_description=__doc__,
    py_modules=['flask_loguru'],
    # if you would be using a package instead use packages instead
    # of py_modules:
    # packages=['flask_sqlite3'],
    zip_safe=False,
    include_package_data=True,
    platforms='any',
    install_requires=[
        'Flask'
    ],
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]
)
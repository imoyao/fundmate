#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/27 18:08
"""
类比DRF中的serializer
"""
from apiflask import Schema
from apiflask.fields import Email, Integer, String
from apiflask.validators import Length


class UserOutSchema(Schema):
    id = Integer()
    username = String()
    email = Email()


class UserInSchema(Schema):
    username = String(required=True, validate=Length(5, 25))
    password = String(required=True, validate=Length(6, 40))
    email = Email(required=True, validate=Length(6, 40))

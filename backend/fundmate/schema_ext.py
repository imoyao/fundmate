#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/5/24 15:19
"""
公用schema提取
"""
from apiflask import Schema
from apiflask.fields import Boolean, Email, String
from apiflask.validators import Equal, Length
from marshmallow import ValidationError, pre_load

from backend.fundmate.user.models import User


class UserInSchema(Schema):
    username = String(required=True, validate=Length(5, 25))
    password = String(required=True, validate=Length(6, 40))
    email = Email(required=True, validate=Length(6, 40))
    is_activated = Boolean()

    # kwargs:[TypeError: pre_load() got an unexpected keyword argument 'many' · Issue #1630 · marshmallow-code/marshmallow](https://github.com/marshmallow-code/marshmallow/issues/1630)
    @pre_load(pass_many=True)
    def register_validate(self, data, **kwargs):
        """Validate the form."""
        user = User.query.filter_by(username=data.get('username')).first()
        if user:
            raise ValidationError("Username already registered")
        user = User.query.filter_by(email=data.get('email')).first()
        if user:
            raise ValidationError("Email already registered")
        return data


class RegisterSchema(UserInSchema):
    re_password = String(required=True, validate=(Length(6, 40), Equal('password')))




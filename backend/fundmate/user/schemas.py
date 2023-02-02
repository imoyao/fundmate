#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/27 18:08
"""
类比DRF中的serializer
"""
from __future__ import annotations

import typing

from apiflask import Schema
from apiflask.fields import Email, Integer, String
from apiflask.validators import Length, Regexp

from marshmallow import ValidationError, pre_load, validates_schema
from marshmallow.validate import And  # FIXME: 等到apiflask更新之后从它中导入

from backend.fundmate import settings
from backend.fundmate.user.models import User


class UserOutSchema(Schema):
    id = Integer()
    username = String()
    email = Email()


class UserLoginSchema(Schema):
    username = String(required=True)
    password = String(required=True)


password_validation = And(Length(6, 40), Regexp(settings.PASSWORD_REG, error='请提高密码复杂度后重试。'))


class UserInSchema(Schema):
    username = String(validate=Length(3, 25))
    email = Email(validate=Length(6, 40))
    password = String(required=True, validate=password_validation)

    # kwargs:[TypeError: pre_load() got an unexpected keyword argument 'many' · Issue #1630 ·
    # marshmallow-code/marshmallow](https://github.com/marshmallow-code/marshmallow/issues/1630)
    @pre_load(pass_many=True)
    def register_validate(self, data, **kwargs):
        """Validate the form."""
        user = User.query.filter_by(username=data.get('username')).one_or_none()
        if user:
            raise ValidationError("用户名已经存在，请尝试更换用户名后重试。")
        user = User.query.filter_by(email=data.get('email')).one_or_none()
        if user:
            raise ValidationError("该邮箱已经注册，请检查收件箱或者尝试重新找回密码。")
        return data

    @validates_schema(skip_on_field_errors=False)
    def validate_username_or_email_at_least(
            self,
            data: (typing.Mapping[str, typing.Any] | typing.Iterable[typing.Mapping[str, typing.Any]]),
            **kwargs,
    ) -> dict[str, list[str]]:
        """
        对于用户名和密码，必须有一个是为必传参数

        And there are two decorators to register a validation method:

        validates(field_name): to register a method to validate a specified field
        validates_schema: to register a method to validate the whole schema

        **note**
        When using the validates_schema, notice the skip_on_field_errors is set to True as default:

        If skip_on_field_errors=True, this validation method will be skipped whenever validation errors
         have been detected when validating fields.

        see also:
        1. https://github.com/marshmallow-code/marshmallow/issues/675
        2. https://marshmallow.readthedocs.io/en/latest/extending.html#schema-level-validation
        :param data:
        :param kwargs:
        :return:
        """
        username = data.get('username')
        email = data.get('email')
        if not any([username, email]):
            raise ValidationError('username or email at least one is required.')


class ForgetPasswordSchema(Schema):
    email = Email(required=True)


class DenyUserSchema(Schema):
    email = Email()
    username = String()

    @validates_schema(skip_on_field_errors=False)
    def validate_username_or_email_at_least(
            self,
            data: (typing.Mapping[str, typing.Any] | typing.Iterable[typing.Mapping[str, typing.Any]]),
            **kwargs,
    ) -> dict[str, list[str]]:
        """
        :param data:
        :param kwargs:
        :return:
        """
        username = data.get('username')
        email = data.get('email')
        if not any([username, email]):
            raise ValidationError('username or email at least one is required.')


class ResetPasswordSchema(Schema):
    password = String(required=True, validate=password_validation)

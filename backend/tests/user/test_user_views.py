# -*- coding: utf-8 -*-
"""
@Time ： 2022/12/25 17:13
@File ：test_user_views.py
@IDE ：PyCharm
"""
import copy

from flask_praetorian.constants import IS_REGISTRATION_TOKEN_CLAIM, IS_RESET_TOKEN_CLAIM, AccessType

import pytest

from backend.fundmate.errors import ConfirmedFirstError, NoLookupUserError, StatusCodeError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.user.models import User


def delete_user(user_inst):
    """验证完成删除用户"""
    user_inst.delete()


def test_get_user(app, client):
    rv = client.get('users/')
    assert rv.status_code == 200
    assert not rv.json


@pytest.mark.parametrize('data,resp_body', [
    ({'username': 'foo', 'password': 'foobar2000', 'email': 'foo@bar.com'}, {
        "message": {
            "json": {
                "_schema": [
                    "用户名已经存在，请尝试更换用户名后重试。"
                ]
            }
        }
    }),
    ({'username': 'foobar1', 'password': 'foobar2000', 'email': 'foo@bar.com'}, {
        "message": {
            "json": {
                "_schema": [
                    "该邮箱已经注册，请检查收件箱或者尝试重新找回密码。"
                ]
            }
        }
    }),
    ({'username': 'foobar1', 'password': 'foobar2000', 'email': 'foobaz@bar.com'}, {
        "message": "注册激活邮件已成功发送给用户：foobar1"}
     ),
    ({'username': 'foobar2', 'password': '123456', 'email': 'foobaz1@bar.com'},
     {'message': {'json': {'password': ['请提高密码复杂度洁后重试。']}}}
     )])
def test_register(app, client, data, resp_body, request):
    result = client.post("users/register", json=data)
    logger.info(result.json)
    assert result
    if data.get('username') == 'foo' or data.get('email') == 'foo@bar.com':
        assert result.status_code == 400
    else:
        if result.status_code == 400:
            assert result.json.get('message').get('json')
        else:
            assert result.status_code == 200
            email = data.get('email')
            _user_inst = User.lookup(email)

            request.addfinalizer(lambda: delete_user(_user_inst))

    assert result.json == resp_body


@pytest.mark.parametrize('data', [
    ({'username': 'test_foo', 'password': 'foobar2000', 'email': 'test_foo@bar.com'})])
def test_confirm_and_active_account(app, client, default_guard, mail, data, request):
    """
    向用户发送邮件，并且根据邮件中的携带信息发送请求测试可以通过认证
    :return:
    """
    email = data.get('email')
    result = client.post("users/register", json=data)
    assert result
    assert result.status_code == 200
    before_confirm_user_inst = User.lookup(email)
    assert before_confirm_user_inst
    assert not before_confirm_user_inst.is_confirmed
    assert before_confirm_user_inst.is_active
    with app.mail.record_messages() as outbox:
        notify = default_guard.send_registration_email(
            email,
            user=before_confirm_user_inst,
            confirmation_sender=app.config['PRAETORIAN_CONFIRMATION_SENDER'],
        )
        token = notify.get("token")
        # test our own interpretation and what we got back from flask_mail
        msg = notify.get("message")
        assert token in msg
        assert msg == outbox[0].html
        assert not notify.get("result")

    # test our token is good
    jwt_data = default_guard.extract_jwt_token(
        token,
        access_type=AccessType.register,
    )
    assert jwt_data.get(IS_REGISTRATION_TOKEN_CLAIM)
    _headers = {'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': "Bearer " + token}
    result = client.get("users/confirmation", headers=_headers)
    assert result.status_code == 200

    after_confirm_user_inst = User.lookup(email)
    assert after_confirm_user_inst.is_confirmed
    assert after_confirm_user_inst.is_active
    json_result = result.json
    assert json_result
    logger.info(json_result)
    assert 'access_token' in json_result
    # addfinalizer 函数传参：https://stackoverflow.com/a/72184887
    request.addfinalizer(lambda: delete_user(after_confirm_user_inst))


def test_login(app, client, default_guard, mail, request):
    data = {'username': app.config.get('TEST_USERNAME'), 'password': app.config.get('TEST_PASSWORD'),
            'email': app.config.get('TEST_EMAIL')}
    email = data.get('email')

    def try_login(login_data):
        _result = client.post("users/login", json=login_data)
        return _result

    user_inst = User.lookup(email)
    assert user_inst.is_confirmed

    # 将用户置为未确认
    user_inst.update(is_confirmed=False)
    assert not user_inst.is_confirmed

    # 测试未确认邮件登录
    result = try_login(data)
    assert not result.status_code == 200
    resp = result.json
    msg = resp.get('message')
    error_code = resp.get('error_code')
    assert msg
    assert msg == ConfirmedFirstError.message
    assert error_code == StatusCodeError.CONFIRMED_FIRST_ERR.code

    # 置为确认
    user_inst.update(is_confirmed=True)
    assert user_inst.is_confirmed

    # 登录流程
    # 测试错误密码登录
    login_with_error_pw = copy.deepcopy(data)
    login_with_error_pw['password'] = '_hack' + data.get('password')
    error_result = try_login(login_with_error_pw)
    assert error_result.status_code != 200
    logger.info(error_result.json)
    assert 'access_token' not in error_result.json

    # 测试错误认证信息登录
    login_with_input_error = {'username': 'test_fo', 'password': data.get('password')}
    result_error_username = try_login(login_with_input_error)
    error_resp = result_error_username.json
    assert result_error_username.status_code != 200
    assert 'access_token' not in error_resp
    assert 'message' in error_resp
    assert 'error_code' in error_resp
    error_msg = error_resp.get('message')
    error_code = error_resp.get('error_code')
    assert error_msg
    assert error_msg == NoLookupUserError.message
    assert error_code == StatusCodeError.NO_LOOKUP_USER_ERR.code

    # 测试用户名登录
    login_with_username = {'username': data.get('username'), 'password': data.get('password')}
    result1 = try_login(login_with_username)
    assert result1.status_code == 200
    assert 'access_token' in result1.json

    # 测试邮箱登录
    login_with_email = {'email': data.get('email'), 'password': data.get('password')}
    result2 = try_login(login_with_email)
    assert result2.status_code == 200
    assert 'access_token' in result2.json

    request.addfinalizer(lambda: delete_user(user_inst))


@pytest.mark.parametrize('data', [
    ({'email': 'foo@bar.com'}),
    ({'email': 'foo1@bar1.com'}),
    ({'username': 'foo', 'email': 'foo@bar.com'}),
    ({'username': 'test_foo', 'password': 'foobar2000'}),
])
def test_send_forget_password(app, client, default_guard, mail, data):
    result = client.post("users/forget_password", json=data)
    assert result
    user = User.lookup(data.get('email'))
    if user and len(data) == 1:
        assert result.status_code == 200
        with app.mail.record_messages() as outbox:
            # test a good username
            notify = default_guard.send_reset_email(
                email=user.email,
                reset_sender=app.config['PRAETORIAN_CONFIRMATION_SENDER'],
            )
            token = notify["token"]

            # test our own interpretation and what we got back from flask_mail
            assert token in notify["message"]
            assert notify["message"] == outbox[0].html

            assert not notify["result"]

        # test our token is good
        jwt_data = default_guard.extract_jwt_token(
            notify["token"],
            access_type=AccessType.reset,
        )
        assert jwt_data[IS_RESET_TOKEN_CLAIM]

        validated_user = default_guard.validate_reset_token(token)
        assert validated_user == user
        # request.addfinalizer(lambda: delete_user(user))
    else:
        logger.info(f'{result.status_code}')
        # 请求参数不对
        if result.status_code == 400:
            if len(data) == 1 and data.get('email'):
                resp = result.json
                error_code = resp.get('error_code')
                msg = resp.get('message')
                assert msg == NoLookupUserError.message
                assert error_code == StatusCodeError.NO_LOOKUP_USER_ERR.code

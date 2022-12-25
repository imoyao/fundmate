# -*- coding: utf-8 -*-
"""参考 [Flask Rest API -Part:5- Password Reset - DEV Community](
https://dev.to/paurakhsharma/flask-rest-api-part-5-password-reset-2f2e)

https://github.com/dusktreader/flask-praetorian-tutorial/blob/master/api/src/resources.py
注册登录流程：
1. register
发送token到注册邮箱（要求唯一），用户点击链接回到网页，在网页上将token返回，然后激活用户

2. 登录

验证用户是否激活，只有激活用户才可以登录，登录时验证密码
3. 忘记密码
用户发送token到注册邮箱（三次机会），点击回到网页，在网页中填写新密码，和token一起提交，验证通过更新密码

"""
import traceback

from apiflask import APIBlueprint, PaginationSchema, abort
from flask.views import MethodView
from flask_praetorian import auth_required, current_user, roles_required
from flask_praetorian.exceptions import PraetorianError

import passlib

from backend.fundmate.account.models import Account
from backend.fundmate.account.schemas import AccountOutSchema, CreateAccountSchema
from backend.fundmate.errors import AuthError, ConfirmedFirstError, ForbiddenDenyAdminError, NoLookupUserError
from backend.fundmate.extensions import db, guard
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.schema_ext import EmptySchema
from backend.fundmate.settings import ADMIN_ROLE_NAME
from backend.fundmate.user.models import User
from backend.fundmate.user.schemas import (
    DenyUserSchema,
    ForgetPasswordSchema,
    ResetPasswordSchema,
    UserInSchema,
    UserLoginSchema,
    UserOutSchema,
)
from backend.fundmate.view_ext import paginate_query


bp = APIBlueprint("user", __name__, url_prefix="/users")


def load_user(user_id: str):
    """Load user by ID."""
    return User.get_by_id(int(user_id))


@bp.route('/')
class Users(MethodView):

    @bp.input(PaginationSchema, 'query')
    @bp.output(UserOutSchema)
    def get(self, query):
        """获取所有用户信息"""
        ret = paginate_query(User, query)
        return ret


@bp.route('/<int:user_id>')
class UserDetail(MethodView):

    @bp.output(UserOutSchema)
    def get(self, user_id: str) -> User:
        """获取指定用户信息"""
        user_obj = load_user(user_id)
        return user_obj

    @auth_required
    @bp.input(UserInSchema)
    @bp.output(UserOutSchema)
    def patch(self, user_id: str, data: dict) -> User:
        """更新指定用户信息"""
        _user_obj = load_user(user_id)
        if _user_obj:
            abort(404, message=f"You can't patch an not exists user id {user_id}.")
        _user_obj.update(data)
        return _user_obj

    @auth_required
    @bp.output({}, 204)  # no content
    def delete(self, user_id: str) -> str:
        """删除指定用户"""
        user_obj = load_user(user_id)
        if user_obj is not None:
            user_obj.delete()
        return ''


@bp.post('/register')
@bp.input(UserInSchema)
def register(req):
    """
    用户注册

    Registers a new user by parsing a POST request containing new user info and dispatching an email with a registration token

    .. example::
       $ curl http://localhost:5000/register -X POST \
         -d '{
           "username":"Brandt", \
           "password":"herlifewasinyourhands" \
           "email":"brandt@biglebowski.com"
         }'
    """
    username = req.get('username', None)
    email = req.get('email', None)
    password = req.get('password', None)
    # FIXME: 测试环境使用国内邮箱即可，生产环境需要用 SendGrid 等专用平台，否则会限额，无法使用
    try:
        new_user = User.create(username=username, email=email, password=password)
        guard.send_registration_email(email, user=new_user)
        result = {'message': '注册激活邮件已成功发送给用户：{}'.format(new_user.username)}
    except PraetorianError as e:
        logger.error(f"Couldn't send registration email: {e}")
        db.session.rollback()
        result = {'message': f'用户 {username} 注册失败。'}
    return result


@bp.get('/confirmation')
@bp.doc(security='Bearer')
def confirm_and_active_account():
    """
    将register用户携带的token放到header中，然后请求完成注册

    Finalizes a user registration with the token that they were issued in their
    registration email

    基本流程如下：
    1. 用户注册之后向注册邮箱发送确认邮件
    2. 用户点击或访问链接进入站内
    3. 解析用户get请求带的参数，将token放到headers中
    4. 请求该接口，验证token，如果通过则验证确认并激活用户
    5. 完成注册流程

    .. example::
       $ curl http://localhost:5000/confirmation -X GET \
         -H "Authorization: Bearer <your_token>"
    """
    registration_token = guard.read_token_from_header()
    user = guard.get_user_from_registration_token(registration_token)
    if user:
        user.update(is_confirmed=True)
        result = {'access_token': guard.encode_jwt_token(user)}
        return result
    else:
        raise NoLookupUserError


@bp.post('/login')
@bp.input(UserLoginSchema)
def login(data):
    """
    登录功能

    此处的username可以是`email`或者`username`，支持用户名和密码登录
    :param data:
    :return:
    """
    # the username can be username or email
    user_identify = data.get('username', None) or data.get('email', None)
    password = data.get("password", None)
    try:
        user = guard.authenticate(user_identify, password)
    except passlib.exc.UnknownHashError as e:
        logger.error(f'认证失败: {traceback.print_exc()}')
        raise AuthError from e
    if user:
        # 对于active 字段，`flask_praetorian`会默认校验
        is_user_confirmed = user.is_confirmed
        if is_user_confirmed:
            result = {"access_token": guard.encode_jwt_token(user)}
            return result
        else:
            raise ConfirmedFirstError
    raise NoLookupUserError


@bp.get('/refresh_token')
@bp.doc(security='Bearer')
def refresh_token():
    """
    刷新token

    Refreshes an existing JWT by creating a new one that is a copy of the old
    except that it has a refreshed access expiration.

    .. example::
       $ curl http://localhost:5000/refresh -X GET \
         -H "Authorization: Bearer <your_token>"
    """
    old_token = guard.read_token_from_header()
    new_token = guard.refresh_jwt_token(old_token)
    ret = {'access_token': new_token}
    return ret


@bp.post('/forget_password')
@bp.input(ForgetPasswordSchema())
def forget_password(data):
    """
    用户忘记密码

    首先发送邮件给用户，确认本人操作

    :param data:
    :return:
    """
    email = data.get('email')
    user = User.query.filter_by(email=email).one_or_none()
    if user:
        guard.send_reset_email(email)
        result = {'message': '请检查邮箱以完成密码重置。'}
    else:
        raise NoLookupUserError
    return result


@bp.post('/reset_password')
@bp.input(ResetPasswordSchema)
@bp.doc(security='Bearer')
def reset_password(data):
    """
    重置密码

    用户点击邮箱中收到的链接，进入重置流程，输入新的密码更新用户密码

    :param data:
    :return:
    """
    password = data.get('password')
    reset_token = guard.read_token_from_header()
    user = guard.validate_reset_token(reset_token)
    if user:
        hash_password = user.set_password(password)
        user.update(password=hash_password)
        result = {'access_token': guard.encode_jwt_token(user)}
        return result
    else:
        raise NoLookupUserError


@bp.post('/deny')
@auth_required
@roles_required(ADMIN_ROLE_NAME)
@bp.doc(security='Bearer')
@bp.input(DenyUserSchema)
def disable_user(req):
    """
    管理员禁用用户
    Disables a user in the data store
    .. example::
        $ curl http://localhost:5000/disable_user -X POST \
          -H "Authorization: Bearer <your_token>" \
          -d '{"username":"Walter"}'
    """
    user_identify = req.get('username') or req.get('email')
    user = User.lookup(user_identify)
    if ADMIN_ROLE_NAME in user.rolenames:
        raise ForbiddenDenyAdminError
    user.update(is_active=False)
    return {'message': f'用户 {user.username} 已禁用。'}


@bp.post('/activations')
@auth_required
@roles_required(ADMIN_ROLE_NAME)
@bp.doc(security='Bearer')
@bp.input(DenyUserSchema)
def active_user(req):
    """
    系统管理员激活用户

    active a user in the data store

    .. example::
        $ curl http://localhost:5000/disable_user -X POST \
          -H "Authorization: Bearer <your_token>" \
          -d '{"username":"Walter"}'
    """
    user_identify = req.get('username') or req.get('email')
    user = User.lookup(user_identify)
    user.update(is_active=True)
    return {'message': '用户 {} 已重新激活。'.format(user.username)}


@bp.route('/<int:user_id>/favors')
@auth_required
class UserFavorFunds(MethodView):
    """
    用户关注的基金
    """

    def get(self, user_id: str):
        """获取自选基金信息"""
        user_obj = User.get_by_id(int(user_id))
        return user_obj

    def post(self, user_id: str, fund_id: str):
        """用户关注基金"""
        pass

    def delete(self, user_id: str, fund_id: str):
        """用户取消关注基金"""
        pass


@bp.route('/accounts')
class UserAccounts(MethodView):
    """
    用户账本
    """
    account_links = {
        'getAccountByUserId': {
            'operationId': 'getUserAccount',
            'parameters': {
                'userId': '$request.path.id'
            }
        }
    }

    @auth_required
    @bp.input(EmptySchema)
    @bp.output(AccountOutSchema(many=True))
    @bp.doc(security='Bearer')
    def get(self, account_type: str):
        """获取用户账本信息
        根据类型查询自己名下的账户，账户按照类型区分：
        支持all,stock,fund,bank,
        """
        user = current_user()
        user_id = user.id
        if account_type:
            accounts = Account.query.filter(creator_id=user_id, account_type=account_type)
        else:
            accounts = Account.query.filter_by(creator_id=user_id)
        return accounts

    @auth_required
    @bp.input(CreateAccountSchema)
    @bp.output(AccountOutSchema, links=account_links)
    @bp.doc(security='Bearer')
    def post(self, data: dict):
        """创建用户账本"""
        user = current_user()
        user_id = user.id
        data['creator_id'] = user_id
        account = Account.create(**data)
        return account

    @auth_required
    @bp.doc(security='Bearer')
    def delete(self, fund_id: str):
        """删除用户账本"""
        pass

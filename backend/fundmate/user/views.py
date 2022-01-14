# -*- coding: utf-8 -*-
"""
参考 [Flask Rest API -Part:5- Password Reset - DEV Community](https://dev.to/paurakhsharma/flask-rest-api-part-5-password-reset-2f2e)
注册登录流程：
1. register
发送token到注册邮箱（要求唯一），用户点击链接回到网页，在网页上将token返回，然后激活用户
2. 登录
验证用户是否激活，只有激活用户才可以登录，登录时验证密码
3. 忘记密码
用户发送token到注册邮箱（三次机会），点击回到网页，在网页中填写新密码，和token一起提交，验证通过更新密码

"""
from apiflask import APIBlueprint, PaginationSchema, abort, auth_required, input, output
from flask.views import MethodView

import flask_praetorian

from backend.fundmate.account.models import Account
from backend.fundmate.account.schemas import AccountOutSchema, CreateAccountSchema
from backend.fundmate.errors import ConfirmedFirst, NoLookupUser
from backend.fundmate.extensions import db, guard
from backend.fundmate.schema_ext import EmptySchema
from backend.fundmate.user.models import User
from backend.fundmate.user.schemas import (
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

    @input(PaginationSchema, 'query')
    @output(UserOutSchema)
    def get(self, query):
        """获取所有用户信息"""
        ret = paginate_query(User, query)
        return ret

    # @input(UserInSchema)
    # @output(UserOutSchema)
    # def post(self, data: dict) -> User:
    #     """新建用户"""
    #     _user_obj = User.create(**data)
    #     print(_user_obj, '--_user_obj--')
    #     return _user_obj


@bp.route('/<int:user_id>')
class UserDetail(MethodView):

    @output(UserOutSchema)
    def get(self, user_id: str) -> User:
        """获取指定用户信息"""
        user_obj = load_user(user_id)
        return user_obj

    @input(UserInSchema(partial=True))
    @output(UserOutSchema)
    def patch(self, user_id: str, data: dict) -> User:
        """更新指定用户信息"""
        _user_obj = load_user(user_id)
        if _user_obj:
            abort(404, message=f"You can't patch an not exists user id {user_id}.")
        user = User.save(data)
        return user

    @output({}, 204)  # no content
    def delete(self, user_id: str) -> str:
        """删除指定用户"""
        user_obj = load_user(user_id)
        if user_obj is not None:
            User.delete(user_obj)
        return ''


@bp.post('/login')
@input(UserLoginSchema(partial=True))
def login(data):
    username = data.get("username", None)
    password = data.get("password", None)
    user = guard.authenticate(username, password)
    if user:
        is_user_confirmed = user.is_confirmed
        # FIXME:is_user_active = user.is_active
        if is_user_confirmed:
            result = {"access_token": guard.encode_jwt_token(user)}
            return result
        else:
            raise ConfirmedFirst
    raise NoLookupUser


@bp.post('/register')
@input(UserInSchema())
def register(req):
    """
    Registers a new user by parsing a POST request containing new user info and
    dispatching an email with a registration token
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
    new_user = User.create(username=username, email=email, password=password, synchronize_session=False)
    # FIXME: 测试环境使用国内邮箱即可，生产环境需要用 SendGrid 等专用平台，否则会限额，无法使用
    guard.send_registration_email(email, user=new_user)
    # 邮件发送成功之后再提交数据库创建
    db.session.commit()
    result = {'message': '注册激活邮件已成功发送给用户：{}'.format(new_user.username)}
    return result


@bp.get('/confirmation')
def confirm_and_active_account():
    """
    将register用户携带的token放到header中，然后请求完成注册
    Finalizes a user registration with the token that they were issued in their
    registration email
    .. example::
       $ curl http://localhost:5000/finalize -X GET \
         -H "Authorization: Bearer <your_token>"
    """
    registration_token = guard.read_token_from_header()
    user = guard.get_user_from_registration_token(registration_token)
    if user:
        user.update(is_confirmed=True)
        result = {'access_token': guard.encode_jwt_token(user)}
        return result
    else:
        raise NoLookupUser


@bp.get('/refresh')
def refresh_token():
    """
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


@bp.route('/password/forget', methods=['POST'])
@input(ForgetPasswordSchema())
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
        raise NoLookupUser
    return result


@bp.post('/password/reset')
@input(ResetPasswordSchema())
def reset_password(data):
    """
    重置密码

    用户点击邮箱中收到的链接，进入重置流程，更新用户密码
    :param data:
    :return:
    """
    password = data.get('password')
    reset_token = guard.read_token_from_header()
    user = guard.validate_reset_token(reset_token)
    if user:
        user.update(password=password)
        result = {'access_token': guard.encode_jwt_token(user)}
        return result
    else:
        raise NoLookupUser


@bp.route('/deny', methods=['POST'])
@flask_praetorian.auth_required
@flask_praetorian.roles_required('admin')
def disable_user(req):
    """
    管理员禁用用户
    Disables a user in the data store
    .. example::
        $ curl http://localhost:5000/disable_user -X POST \
          -H "Authorization: Bearer <your_token>" \
          -d '{"username":"Walter"}'
    """
    user = User.query.filter_by(username=req.get('username', None)).one()
    user.update(is_active=False)

    return {'message': 'disabled user {}'.format(user.username)}


# class ForgotPassword(Resource):
#     """
#     TODO: 参考 [Flask Rest API -Part:5- Password Reset - DEV Community](https://dev.to/paurakhsharma/flask-rest-api-part-5-password-reset-2f2e)
#     """
#
#     def post(self):
#         url = request.host_url + 'reset/'
#         try:
#             body = request.get_json()
#             email = body.get('email')
#             if not email:
#                 raise SchemaValidationError
#
#             user = User.objects.get(email=email)
#             if not user:
#                 raise EmailDoesnotExistsError
#
#             expires = datetime.timedelta(hours=24)
#             reset_token = create_access_token(str(user.id), expires_delta=expires)
#
#             return send_email('[Movie-bag] Reset Your Password',
#                               sender='support@movie-bag.com',
#                               recipients=[user.email],
#                               text_body=render_template('email/reset_password.txt', url=url + reset_token),
#                               html_body=render_template('email/reset_password.html', url=url + reset_token))
#         except SchemaValidationError:
#             raise SchemaValidationError
#         except EmailDoesnotExistsError:
#             raise EmailDoesnotExistsError
#         except Exception as e:
#             raise InternalServerError
#
#
# class ResetPassword(Resource):
#
#     def post(self):
#         url = request.host_url + 'reset/'
#         try:
#             body = request.get_json()
#             reset_token = body.get('reset_token')
#             password = body.get('password')
#
#             if not reset_token or not password:
#                 raise SchemaValidationError
#
#             user_id = decode_token(reset_token)['identity']
#
#             user = User.objects.get(id=user_id)
#
#             user.modify(password=password)
#             user.hash_password()
#             user.save()
#
#             return send_email('[Movie-bag] Password reset successful',
#                               sender='support@movie-bag.com',
#                               recipients=[user.email],
#                               text_body='Password reset was successful',
#                               html_body='<p>Password reset was successful</p>')
#
#         except SchemaValidationError:
#             raise SchemaValidationError
#         except ExpiredSignatureError:
#             raise ExpiredTokenError
#         except (DecodeError, InvalidTokenError):
#             raise BadTokenError
#         except Exception as e:
#             raise InternalServerError


@bp.route('/<int:user_id>/favors')
@flask_praetorian.auth_required
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


@bp.route('/<int:user_id>/accounts')
class UserAccounts(MethodView):
    """
    用户所拥有的账本
    """

    # @input(PaginationSchema, 'query')
    @input(EmptySchema)
    @output(AccountOutSchema(many=True))
    def get(self, user_id: str, account_type: str):
        """获取用户账本信息
        根据类型查询自己名下的账户，账户按照类型区分：
        支持all,stock,fund,bank,
        """
        if account_type:
            accounts = Account.query.filter(creator_id=user_id, account_type=account_type)
        else:
            accounts = Account.query.filter_by(creator_id=user_id)
        return accounts

    @input(CreateAccountSchema)
    def post(self, data: dict):
        """创建用户账本"""
        account = Account.create(**data)
        return account

    def delete(self, user_id: str, fund_id: str):
        """删除用户账本"""
        pass

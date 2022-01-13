# -*- coding: utf-8 -*-
"""User views."""
from apiflask import APIBlueprint, PaginationSchema, abort, auth_required, input, output
from flask.views import MethodView

import flask_praetorian

from backend.fundmate.account.models import Account
from backend.fundmate.account.schemas import AccountOutSchema, CreateAccountSchema
from backend.fundmate.extensions import auth, db, guard
from backend.fundmate.schema_ext import EmptySchema
from backend.fundmate.user.models import User
from backend.fundmate.user.schemas import (
    RegisterSchema,
    UserAuthOutSchema,
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
# @output(UserAuthOutSchema)
def login(data):
    username = data.get("username", None)
    password = data.get("password", None)
    user = guard.authenticate(username, password)
    ret = {"access_token": guard.encode_jwt_token(user)}
    return ret


# see also:https://github.com/dusktreader/flask-praetorian/blob/master/example/register.py
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
    # hash_password = User.set_password(password)
    new_user = User.create(username=username, email=email, password=password, synchronize_session=False)
    # FIXME: 先发送邮件成功再去创建用户成功，否则用户收不到邮件
    send_result = guard.send_registration_email(email, user=new_user)
    print(send_result, '-----------------')
    db.session.commit()
    ret = {'message': 'successfully sent registration email to user {}'.format(new_user.username)}
    return ret


@bp.get('/finalize')
def finalize():
    """
    将上一步用户携带的token放到header中然后请求完成注册
    Finalizes a user registration with the token that they were issued in their
    registration email
    .. example::
       $ curl http://localhost:5000/finalize -X GET \
         -H "Authorization: Bearer <your_token>"
    """
    registration_token = guard.read_token_from_header()
    user = guard.get_user_from_registration_token(registration_token)
    # perform 'activation' of user here...like setting 'active' or something
    ret = {'access_token': guard.encode_jwt_token(user)}
    return ret


@bp.route('/refresh', methods=['GET'])
def refresh():
    """
    Refreshes an existing JWT by creating a new one that is a copy of the old
    except that it has a refrehsed access expiration.
    .. example::
       $ curl http://localhost:5000/refresh -X GET \
         -H "Authorization: Bearer <your_token>"
    """
    old_token = guard.read_token_from_header()
    new_token = guard.refresh_jwt_token(old_token)
    ret = {'access_token': new_token}
    return ret


@bp.route('/reset_pw', methods=['POST'])
def reset_password(data):
    email = data.get('email')
    try:

        guard.send_reset_email(email)
        return Response(json.dumps({'message': 'Please check your email to change the password'}),
                        status=200,
                        mimetype='application/json')
    except (ValueError, KeyError, MissingUserError, PraetorianError):
        return Response(json.dumps({'message': 'Fail to send reset password email'}),
                        status=200,
                        mimetype='application/json')


@bp.route('/deny', methods=['POST'])
@flask_praetorian.auth_required
@flask_praetorian.roles_required('admin')
def disable_user(req):
    """
    禁用某用户
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
@auth_required(auth)
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
        print(data)
        account = Account.create(**data)
        return account

    def delete(self, user_id: str, fund_id: str):
        """删除用户账本"""
        pass

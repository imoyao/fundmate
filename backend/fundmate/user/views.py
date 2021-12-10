# -*- coding: utf-8 -*-
"""User views."""
from apiflask import APIBlueprint, abort, auth_required, input, output
from flask.views import MethodView

from backend.fundmate.account.models import Account
from backend.fundmate.account.schemas import AccountOutSchema, CreateAccountSchema
from backend.fundmate.base_scheme import EmptySchema, PaginationSchema
from backend.fundmate.extensions import auth
from backend.fundmate.user.models import User
from backend.fundmate.user.schemas import UserInSchema, UserOutSchema
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

    @input(UserInSchema)
    @output(UserOutSchema)
    def post(self, data: dict) -> User:
        """新建用户"""
        _user_obj = User.create(**data)
        print(_user_obj, '--_user_obj--')
        return _user_obj


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
        """获取指定用户信息"""
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


@bp.route('/<int:user_id>/favors')
@auth_required(auth)
class UserFavorFunds(MethodView):
    """
    某人关注的基金
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

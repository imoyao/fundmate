# -*- coding: utf-8 -*-
"""User views."""
from typing import Optional

from apiflask import APIBlueprint, Schema, abort, input, output
from apiflask.fields import Boolean, Email, Integer, String
from apiflask.validators import Length
from flask.views import MethodView

from backend.fundmate.account.models import Account
from backend.fundmate.account.schemas import AccountOutSchema
from backend.fundmate.base_scheme import EmptySchema, PaginationSchema
from backend.fundmate.extensions import login_manager
from backend.fundmate.user.models import User
from backend.fundmate.view_ext import paginate_query

bp = APIBlueprint("user", __name__, url_prefix="/users")

# blueprint = Blueprint("user", __name__, url_prefix="/users", static_folder="../static")


@login_manager.user_loader
def load_user(user_id: str):
    """Load user by ID."""
    return User.get_by_id(int(user_id))


class UserOutSchema(Schema):
    id = Integer()
    name = String()
    email = Email(validate=Length(6, 40))


class UserInSchema(Schema):
    username = String(required=True, validate=Length(5, 25))
    password = String(required=True, validate=Length(6, 40))
    email = Email(required=True, validate=Length(6, 40))
    is_activated = Boolean()


@bp.route('/')
class Users(MethodView):

    @input(PaginationSchema, 'query')
    @output(UserOutSchema)
    def get(self, query):
        """获取所有用户信息"""
        ret = paginate_query(User, query)
        return ret

    @input(UserInSchema)
    def post(self, data: dict) -> User:
        """新建用户"""
        print(data, '========uuuupppp======')
        # username = data.pop('username')
        # password = data.pop('password')
        # email = data.pop('email')
        # print(data,'====aft==========')
        _user_obj = User.create(**data)
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
            abort(404)
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
class UserFavorFunds(MethodView):
    """
    某人关注的基金
    """

    @output(UserOutSchema)
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

    def post(self, user_id: str, account_type: str, comment: Optional[str]):
        """创建用户账本"""
        pass

    def delete(self, user_id: str, fund_id: str):
        """删除用户账本"""
        pass

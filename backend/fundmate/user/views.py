# -*- coding: utf-8 -*-
"""User views."""
from apiflask import Schema, input, output, abort, APIBlueprint
from apiflask.fields import Integer, String, Boolean, Email
from apiflask.validators import Length, Range
from flask_login import login_required
from flask.views import MethodView
from apiflask import pagination_builder

from backend.fundmate.user.models import User
from backend.fundmate.extensions import login_manager

bp = APIBlueprint("user", __name__, url_prefix="/users")


# blueprint = Blueprint("user", __name__, url_prefix="/users", static_folder="../static")


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID."""
    return User.get_by_id(int(user_id))


def paginate_query(cls, query_args:dict) -> dict:
    pagination = cls.query.paginate(
        page=query_args['page'],
        per_page=query_args['per_page']
    )
    _items = pagination.items
    return {
        'items': _items,
        'pagination': pagination_builder(pagination)
    }


class UserOutSchema(Schema):
    id = Integer()
    name = String()
    email = Email(validate=Length(6, 40))


class UserInSchema(Schema):
    username = String(required=True, validate=Length(5, 25))
    password = String(required=True, validate=Length(6, 40))
    email = Email(validate=Length(6, 40))
    is_activated = Boolean()


class QuerySchema(Schema):
    page = Integer(missing=1)
    per_page = Integer(missing=20, validate=Range(max=30))


@bp.route('/')
class Users(MethodView):

    @input(QuerySchema, 'query')
    @output(UserOutSchema)
    def get(self, query):
        ret = paginate_query(User, query)
        return ret


@bp.route('/<int:user_id>')
class UserDetail(MethodView):

    @output(UserOutSchema)
    def get(self, user_id):
        """获取指定用户信息"""
        user_obj = load_user(user_id)
        return user_obj

    def post(self):
        """
        新建用户
        """
        return {'message': 'Hello,User!'}

    @input(UserInSchema(partial=True))
    @output(UserOutSchema)
    def patch(self, user_id, data):
        """获取指定用户信息"""
        _user_obj = load_user(user_id)
        if _user_obj:
            abort(404)
        user = User.save(data)
        return user

    @output({}, 204)  # no content
    def delete(self, user_id):
        """删除指定用户"""
        user_obj = load_user(user_id)
        if user_obj is not None:
            _user = User.delete(user_obj)
        return ''

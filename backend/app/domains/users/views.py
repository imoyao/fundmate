# -*- coding: utf-8 -*-
"""用户 API — 当前家庭成员列表（个人中心 / 家庭成员管理前置）。

鉴权说明：非白名单接口需登录；成员列表按当前用户所属家庭过滤（D1 家庭共享）。
"""

from apiflask import APIBlueprint
from flask import jsonify

from app.core.auth import get_family_id
from app.core.database import get_db
from app.domains.users.models import ROLE_LABELS, User
from app.domains.users.schemas import UserOut

users_bp = APIBlueprint('users', __name__, url_prefix='/api/users')


def _user_to_dict(user: User) -> dict:
    data = UserOut.model_validate(user).model_dump()
    data['role_label'] = ROLE_LABELS.get(user.role, user.role)
    return data


@users_bp.get('/')
def list_family_members():
    """获取当前用户所属家庭的成员列表。"""
    with get_db() as db:
        members = db.query(User).filter(User.family_id == get_family_id()).order_by(User.created_at.asc()).all()
        return jsonify({'data': [_user_to_dict(m) for m in members], 'message': 'ok'})

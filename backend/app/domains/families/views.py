# -*- coding: utf-8 -*-
"""家庭 API — 创建家庭、查看成员（D1 分权管理）。

创建家庭：当前用户迁入新家庭并成为主理人（admin）；
查看成员：仅主理人可查看（require_roles('admin')）。
"""

from apiflask import APIBlueprint
from flask import abort, g, jsonify

from app.core.auth import require_roles
from app.core.database import get_db
from app.core.validation import parse_body
from app.domains.families.models import Family
from app.domains.families.schemas import FamilyCreate, FamilyOut
from app.domains.users.models import ROLE_ADMIN, ROLE_LABELS, User

families_bp = APIBlueprint('families', __name__, url_prefix='/api/families')


def _family_to_dict(family: Family) -> dict:
    return FamilyOut.model_validate(family).model_dump()


@families_bp.post('/')
def create_family():
    """创建家庭，当前用户自动成为主理人。"""
    data = parse_body(FamilyCreate)
    name = data.name.strip()
    if not name:
        abort(400, description='家庭名称不能为空')

    with get_db() as db:
        family = Family(name=name)
        db.add(family)
        db.flush()

        user = db.query(User).filter_by(id=g.current_user.id).first()
        if not user:
            db.rollback()
            abort(401, description='未登录')

        user.family_id = family.id
        user.role = ROLE_ADMIN
        db.commit()
        db.refresh(family)
        return jsonify({'data': _family_to_dict(family), 'message': 'ok'})


@families_bp.get('/<int:family_id>/members/')
@require_roles(ROLE_ADMIN)
def list_family_members(family_id: int):
    """查看指定家庭成员（仅主理人）。"""
    with get_db() as db:
        family = db.query(Family).get(family_id)
        if not family:
            abort(404, description='家庭不存在')
        members = db.query(User).filter(User.family_id == family_id).order_by(User.created_at.asc()).all()
        data = [
            {
                'id': u.id,
                'username': u.username,
                'nickname': u.nickname,
                'avatar': u.avatar,
                'email': u.email,
                'role': u.role,
                'role_label': ROLE_LABELS.get(u.role, u.role),
                'is_active': u.is_active,
            }
            for u in members
        ]
        return jsonify({'data': data, 'message': 'ok'})

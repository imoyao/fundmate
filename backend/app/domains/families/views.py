# -*- coding: utf-8 -*-
"""家庭 API — 创建家庭、成员管理（D1 分权管理 / #1173）。

- 创建家庭：当前用户迁入新家庭并成为主理人（admin）；
- 成员管理（列表 / 邀请 / 改角色 / 移除）：仅主理人，作用域固定为当前家庭。

成员业务规则（邮箱认领、最后一名主理人守卫、账户归属置空）在
`app/services/family_member_service.py`，本模块只做鉴权、归属校验与响应组织。
"""

from apiflask import APIBlueprint
from flask import abort, g, jsonify

from app.core.auth import get_family_id, require_roles
from app.core.database import get_db
from app.core.validation import parse_body
from app.domains.families.models import Family
from app.domains.families.schemas import FamilyCreate, FamilyMemberCreate, FamilyMemberUpdate, FamilyOut
from app.domains.users.models import ROLE_ADMIN, User
from app.services import family_member_service as member_svc

families_bp = APIBlueprint('families', __name__, url_prefix='/api/families')


def _family_to_dict(family: Family) -> dict:
    return FamilyOut.model_validate(family).model_dump()


def _assert_own_family(db, family_id: int) -> None:
    """作用域守卫：只能操作**自己所属**的家庭。

    别的家庭一律 404 而非 403 —— 与 `get_owned_or_404` 同一口径（不泄露存在性）。
    """
    if family_id != get_family_id() or db.get(Family, family_id) is None:
        abort(404, description='家庭不存在')


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
        db.flush()
        db.refresh(family)
        return jsonify({'data': _family_to_dict(family), 'message': 'ok'})


@families_bp.get('/<int:family_id>/members/')
@require_roles(ROLE_ADMIN)
def list_family_members(family_id: int):
    """查看指定家庭成员（仅主理人）。"""
    with get_db() as db:
        _assert_own_family(db, family_id)
        return jsonify({'data': member_svc.list_members(db, family_id), 'message': 'ok'})


@families_bp.post('/<int:family_id>/members/')
@require_roles(ROLE_ADMIN)
def invite_family_member(family_id: int):
    """邀请成员（仅主理人）：按邮箱预建映射行，对方首次登录时认领。"""
    data = parse_body(FamilyMemberCreate)
    with get_db() as db:
        _assert_own_family(db, family_id)
        try:
            member = member_svc.invite_member(db, family_id, data.email, data.nickname, data.role)
        except member_svc.FamilyMemberError as e:
            abort(e.status_code, description=e.message)
        return jsonify({'data': member, 'message': '邀请已创建，对方用该邮箱首次登录后即加入家庭'})


@families_bp.patch('/<int:family_id>/members/<int:user_id>/')
@require_roles(ROLE_ADMIN)
def update_family_member(family_id: int, user_id: int):
    """修改成员角色 / 昵称（仅主理人）。"""
    data = parse_body(FamilyMemberUpdate)
    with get_db() as db:
        _assert_own_family(db, family_id)
        try:
            member = member_svc.update_member(db, family_id, user_id, data.role, data.nickname)
        except member_svc.FamilyMemberError as e:
            abort(e.status_code, description=e.message)
        return jsonify({'data': member, 'message': 'ok'})


@families_bp.delete('/<int:family_id>/members/<int:user_id>/')
@require_roles(ROLE_ADMIN)
def remove_family_member(family_id: int, user_id: int):
    """移除成员（仅主理人）：删本地映射，其名下账户归属置空。"""
    with get_db() as db:
        _assert_own_family(db, family_id)
        try:
            member_svc.remove_member(db, family_id, user_id, current_user_id=g.current_user.id)
        except member_svc.FamilyMemberError as e:
            abort(e.status_code, description=e.message)
        return jsonify({'data': None, 'message': '已移除'})

# -*- coding: utf-8 -*-
"""家庭成员档案 API（#1173）— 账本账户的「归属维度」。

四个端点：
- GET    /api/families/members/profiles/            列出成员档案
- POST   /api/families/members/profiles/            新增成员档案
- PATCH  /api/families/members/profiles/<id>/       改称谓 / 身份 / 关联账号 / 启用状态
- DELETE /api/families/members/profiles/<id>/       停用成员（软删）

## 为什么单独一个视图文件

`families/views.py` 已有「家庭」与「登录账号成员」两个职责；成员档案是**第三个**
职责（账本归属维度），且带完整 CRUD。若塞进同一个文件，账户域视图会随成员管理的
演进持续变厚——`scripts/check_view_thickness.py` 对既有视图是「只减不增」的冻结基线，
而对新增视图文件有独立判据（lines ≤ 400 / query ≤ 10 / commit ≤ 5）。
先例：`domains/importers/e_account_views.py`（同域第二个蓝图）。

## 两套「成员」不要混（#1173）

- ``GET /api/families/<id>/members/`` → **登录账号**（``users`` 表），带权限角色
  （admin / member / viewer），仅主理人可见；
- 本文件的 ``/members/profiles/`` → **家庭成员档案**（``family_members`` 表），
  是账本账户的归属维度。成员可能没有 App 账号（如「老婆」），故与登录账号解耦。

写操作一律 admin-only；档案读对全角色开放（viewer 也要能看见账户归属是谁，
否则账户列表里会出现无名账户）。

业务规则全在 ``services/family_member_service.py``；本文件只做「入参解析 +
调服务 + 组信封」。
"""

from apiflask import APIBlueprint
from flask import abort, jsonify

from app.core.auth import get_family_id, require_roles
from app.core.database import get_db
from app.core.validation import parse_body
from app.domains.families.models import FamilyMember
from app.domains.families.schemas import FamilyMemberCreate, FamilyMemberUpdate
from app.domains.users.models import ROLE_ADMIN
from app.services.family_member_service import (
    FamilyMemberError,
    create_member,
    deactivate_member,
    get_member,
    list_members,
    update_member,
)

member_bp = APIBlueprint('family_members', __name__, url_prefix='/api/families/members/profiles')


def _member_error(e: FamilyMemberError):
    """业务错误 → 统一信封（与其它域的写法一致：error_code 为空则走 abort）。"""
    if e.error_code is None:
        abort(e.status_code, description=e.message)
    return jsonify({'data': None, 'message': e.message, 'error_code': e.error_code}), e.status_code


def _get_member_or_404(db, member_id: int) -> FamilyMember:
    """取家庭内的成员档案，越权或不存在统一 404（不泄露存在性）。"""
    member = get_member(db, get_family_id(), member_id)
    if member is None:
        abort(404, description='成员不存在或无权访问')
    return member


@member_bp.get('/')
def list_member_profiles():
    """列出家庭成员档案（账本账户的归属维度）。

    对全角色开放：viewer 也要能看见账户归属是谁，否则账户列表里会出现无名账户。
    """
    with get_db() as db:
        data = list_members(db, get_family_id())
        return jsonify({'data': data, 'message': 'ok'})


@member_bp.post('/')
@require_roles(ROLE_ADMIN)
def create_member_profile():
    """新增家庭成员档案（仅主理人）。"""
    data = parse_body(FamilyMemberCreate)
    with get_db() as db:
        try:
            result = create_member(db, get_family_id(), name=data.name, role=data.role)
        except FamilyMemberError as e:
            return _member_error(e)
        return jsonify({'data': result, 'message': 'ok'})


@member_bp.patch('/<int:member_id>/')
@require_roles(ROLE_ADMIN)
def update_member_profile(member_id: int):
    """改家庭成员档案：称谓 / 身份 / 关联账号 / 启用状态（仅主理人）。"""
    data = parse_body(FamilyMemberUpdate)
    with get_db() as db:
        member = _get_member_or_404(db, member_id)
        try:
            result = update_member(
                db, member, name=data.name, role=data.role, user_id=data.user_id, is_active=data.is_active
            )
        except FamilyMemberError as e:
            return _member_error(e)
        return jsonify({'data': result, 'message': 'ok'})


@member_bp.delete('/<int:member_id>/')
@require_roles(ROLE_ADMIN)
def delete_member_profile(member_id: int):
    """停用家庭成员档案（软删，仅主理人）。

    名下有账户的成员不能硬删（否则账户归属悬空），故改为停用并保留历史归属。
    """
    with get_db() as db:
        member = _get_member_or_404(db, member_id)
        result = deactivate_member(db, member)
        return jsonify({'data': result, 'message': 'ok'})

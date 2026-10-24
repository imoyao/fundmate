# -*- coding: utf-8 -*-
"""家庭成员管理业务规则（#1173）：邀请 / 改角色与昵称 / 移除。

WHY 单独一层
    「家庭成员」是 `users` 表的写路径，但它与鉴权身份（`supabase_id` + JIT 建号）
    强耦合：邀请 = **按邮箱预建本地映射行**，对方首次登录时由
    `UserIdentity.provision` 认领（本仓没有 service-role 密钥，后端不创建
    Supabase Auth 账号）。这层语义放在视图里会被 HTTP 细节掩埋，也让「认领」
    与「邀请」两边难以对照维护。

口径
    - 所有函数都以 `family_id` 为第一参数：越权统一由调用方的当前家庭注入，
      不存在「传一个别人家的 id 就能改别人家成员」的路径；
    - 错误一律抛 :class:`FamilyMemberError`（视图转统一信封），文案即面向用户的文案；
    - 事务由请求级边界持有（`get_db` 的 teardown 统一提交/回滚），本层只 `flush()`。

移除的语义（重要）
    `DELETE` 删的是**本地映射行**，Supabase Auth 账号不受影响（无 service-role 密钥
    无法注销云端账号）。后果：该成员下次登录会被 JIT 重新建号并落到默认家庭 1，
    需由目标家庭再次邀请——与「退出家庭」一致，但**不是**注销账号。
    被移除成员名下的账户归属置为 NULL（账户与数据都留在原家庭，不随人走）。
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.ledgers.models import Ledger
from app.domains.users.models import ROLE_ADMIN, ROLE_LABELS, User, UserPreference


class FamilyMemberError(Exception):
    """家庭成员操作失败：视图据此返回统一错误信封。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def member_payload(user: User) -> dict:
    """成员出参（列表与写接口共用，保证字段集一致）。"""
    return {
        'id': user.id,
        'username': user.username,
        'nickname': user.nickname,
        'avatar': user.avatar,
        'email': user.email,
        'role': user.role,
        'role_label': ROLE_LABELS.get(user.role, user.role),
        'is_active': user.is_active,
        # 已邀请未登录：本地行已建、Supabase 身份尚未绑定（前端据此显示「待加入」）
        'pending': user.supabase_id is None,
    }


def list_members(db: Session, family_id: int) -> list[dict]:
    """家庭成员列表，按创建时间升序。"""
    members = db.query(User).filter(User.family_id == family_id).order_by(User.created_at.asc()).all()
    return [member_payload(m) for m in members]


def _get_member(db: Session, family_id: int, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id, User.family_id == family_id).first()
    if user is None:
        raise FamilyMemberError('成员不存在', 404)
    return user


def _admin_count(db: Session, family_id: int) -> int:
    return db.query(func.count(User.id)).filter(User.family_id == family_id, User.role == ROLE_ADMIN).scalar() or 0


def _validate_role(role: str) -> str:
    if role not in ROLE_LABELS:
        raise FamilyMemberError('角色无效（仅支持 admin / member / viewer）', 400)
    return role


def invite_member(db: Session, family_id: int, email: str, nickname: str | None = None, role: str = 'member') -> dict:
    """邀请成员：按邮箱预建本地映射行（`supabase_id` 为空，待首次登录认领）。"""
    email = (email or '').strip().lower()
    if not email or '@' not in email or len(email) > 200:
        raise FamilyMemberError('邮箱格式不正确', 400)
    _validate_role(role)

    existing = db.query(User).filter(func.lower(User.email) == email).first()
    if existing is not None:
        if existing.family_id == family_id:
            raise FamilyMemberError('该邮箱已在家庭成员中', 409)
        # 邮箱是「认领凭据」，跨家庭重复会让首次登录认领到错误家庭，必须显式拒绝
        raise FamilyMemberError('该邮箱已被其他家庭使用', 409)

    nickname = (nickname or '').strip() or email.split('@')[0]
    user = User(
        # 故意留空：这不是「一个没有身份的账号」，而是等 Supabase 首次登录回填的映射位
        supabase_id=None,
        family_id=family_id,
        username=nickname,
        nickname=nickname,
        email=email,
        role=role,
        is_active=1,
    )
    db.add(user)
    db.flush()
    db.refresh(user)
    return member_payload(user)


def update_member(
    db: Session,
    family_id: int,
    user_id: int,
    role: str | None = None,
    nickname: str | None = None,
) -> dict:
    """改角色 / 昵称。降级最后一名主理人会被拒绝（否则家庭再无管理员）。"""
    user = _get_member(db, family_id, user_id)

    if role is not None:
        _validate_role(role)
        if user.role == ROLE_ADMIN and role != ROLE_ADMIN and _admin_count(db, family_id) <= 1:
            raise FamilyMemberError('家庭至少需要一名主理人，请先把其他成员设为主理人', 409)
        user.role = role

    if nickname is not None:
        nickname = nickname.strip()
        if not nickname:
            raise FamilyMemberError('昵称不能为空', 400)
        user.nickname = nickname

    db.flush()
    db.refresh(user)
    return member_payload(user)


def remove_member(db: Session, family_id: int, user_id: int, current_user_id: int) -> None:
    """移除成员：删本地映射行，账户归属置空，私有偏好一并清理。

    - 不能移除自己（否则可能把自己锁在家庭外，且当前请求瞬间变成「已删除用户」）；
    - 不能移除最后一名主理人；
    - `user_preferences` 显式删除：其 FK 声明了 ON DELETE CASCADE，但 SQLite 默认
      未开 `PRAGMA foreign_keys`，指望数据库级联会留孤儿行。
    """
    if user_id == current_user_id:
        raise FamilyMemberError('不能移除自己', 400)
    user = _get_member(db, family_id, user_id)
    if user.role == ROLE_ADMIN and _admin_count(db, family_id) <= 1:
        raise FamilyMemberError('家庭至少需要一名主理人，不能移除最后一名主理人', 409)

    db.query(Ledger).filter(
        Ledger.family_id == family_id,
        Ledger.owner_user_id == user.id,
    ).update({'owner_user_id': None}, synchronize_session=False)
    db.query(UserPreference).filter(UserPreference.user_id == user.id).delete(synchronize_session=False)
    db.delete(user)
    db.flush()

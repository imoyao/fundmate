# -*- coding: utf-8 -*-
"""家庭成员档案业务规则服务层（#1173）。

WHY 下沉
    成员增删改、角色变更、账户归属校验、删除前的连带检查，都是**业务规则 + 校验**，
    不是 HTTP 编排。留在 ``domains/families/views.py`` 里时：① 视图层厚度基线
    （72 行 / 2 次 ORM 查询）只减不增，加端点必超；② 高风险路径没有服务层单测入口。

边界
    - 入参是**已通过家庭归属校验的模型对象**或纯数据，服务层不碰 ``g`` / ``request``，
      故可被非 HTTP 入口复用；
    - 错误一律抛 :class:`FamilyMemberError`，由视图转成统一信封 + 状态码 + error_code；
    - 事务由请求级边界持有（``get_db`` 的 teardown 统一提交/回滚），本层只 ``flush()``。

## 关键口径

- **成员 ≠ 登录账号**：``family_members`` 是资产归属档案，可无账号；
  ``users.role``（admin/member/viewer）是权限角色，与本表 ``role``（户主/配偶/子女）不同语义。
- **删除是软删**：有账户绑定的成员不能硬删（否则 ``ledgers.owner_member_id`` 悬空），
  故改为停用（``is_active=False``），保留历史归属可追溯。
"""

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.families.models import (
    MEMBER_ROLE_LABELS,
    MEMBER_ROLES,
    FamilyMember,
)
from app.domains.ledgers.models import Ledger


class FamilyMemberError(Exception):
    """家庭成员业务错误：视图据此返回统一信封 + 状态码 + error_code。"""

    def __init__(self, message: str, status_code: int = 400, error_code=None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


def member_to_dict(member: FamilyMember, ledger_count: int = 0) -> dict:
    """成员 → 响应体。

    ``ledger_count`` 是该成员名下绑定的账户数——成员列表要显示「绑了几个账户」，
    否则删成员时用户不知道会不会丢数据。
    """
    return {
        'id': member.id,
        'name': member.name,
        'role': member.role,
        'role_label': MEMBER_ROLE_LABELS.get(member.role, member.role),
        'user_id': member.user_id,
        'is_active': bool(member.is_active),
        'ledger_count': ledger_count,
        'created_at': member.created_at.isoformat() if member.created_at else None,
        'updated_at': member.updated_at.isoformat() if member.updated_at else None,
    }


def _validate_name(name: str) -> str:
    """成员称谓：非空、去首尾空白、限长 50（与模型列宽一致）。"""
    cleaned = (name or '').strip()
    if not cleaned:
        raise FamilyMemberError('成员称谓不能为空', 400, 2001)
    if len(cleaned) > 50:
        raise FamilyMemberError('成员称谓过长（最多 50 字）', 400, 2002)
    return cleaned


def _validate_role(role: str) -> str:
    """家庭内角色必须在词表内（不复用 users 的权限角色词表）。"""
    if role not in MEMBER_ROLES:
        raise FamilyMemberError(f'成员角色无效：{role}（可选：{"/".join(MEMBER_ROLES)}）', 400, 2003)
    return role


def list_members(db: Session, family_id: int, include_inactive: bool = True) -> list[dict]:
    """列出家庭成员（含各自名下账户数）。

    ``include_inactive=False`` 时只返启用成员——账户归属下拉用这个
    （已停用的成员不该再被指派新账户，但历史绑定仍要能显示）。
    """
    query = db.query(FamilyMember).filter(FamilyMember.family_id == family_id)
    if not include_inactive:
        query = query.filter(FamilyMember.is_active.is_(True))
    members = query.order_by(FamilyMember.created_at.asc(), FamilyMember.id.asc()).all()

    # 一次聚合拿全成员的账户数（避免 N+1）
    counts = (
        db.query(Ledger.owner_member_id, func.count(Ledger.id))
        .filter(Ledger.family_id == family_id, Ledger.owner_member_id.isnot(None))
        .group_by(Ledger.owner_member_id)
        .all()
    )
    count_map = {mid: cnt for mid, cnt in counts}
    return [member_to_dict(m, count_map.get(m.id, 0)) for m in members]


def create_member(
    db: Session,
    family_id: int,
    *,
    name: str,
    role: str = 'other',
    user_id: int | None = None,
    is_active: bool = True,
) -> dict:
    """新增成员档案。"""
    member = FamilyMember(
        family_id=family_id,
        name=_validate_name(name),
        role=_validate_role(role),
        user_id=user_id,
        is_active=is_active,
    )
    db.add(member)
    db.flush()
    db.refresh(member)
    logger.info(f'[OK] 家庭新增成员：{member.name}（family_id={family_id}, id={member.id}）')
    return member_to_dict(member, 0)


def update_member(
    db: Session,
    member: FamilyMember,
    *,
    name: str | None = None,
    role: str | None = None,
    user_id: int | None = None,
    is_active: bool | None = None,
) -> dict:
    """改成员档案（称谓 / 身份 / 关联账号 / 启用状态）。

    只更新**显式传入**的字段（``None`` 表示「不改」）——因此 ``user_id=None``
    的含义是「**不关联账号**」，**不是**「解绑账号」：解绑要显式传别的值，
    本接口不提供解绑语义（解绑会让成员与账号的对应关系出现空洞，且本项目
    尚无「成员必须绑定账号」的约束，故不引入这个歧义）。
    """
    if name is not None:
        member.name = _validate_name(name)
    if role is not None:
        member.role = _validate_role(role)
    if user_id is not None:
        member.user_id = user_id
    if is_active is not None:
        member.is_active = is_active
    db.flush()
    db.refresh(member)
    ledger_count = (
        db.query(func.count(Ledger.id))
        .filter(Ledger.family_id == member.family_id, Ledger.owner_member_id == member.id)
        .scalar()
        or 0
    )
    return member_to_dict(member, ledger_count)


def deactivate_member(db: Session, member: FamilyMember) -> dict:
    """停用成员（软删）。

    ## 为什么不是硬删

    成员名下可能绑着账户（``ledgers.owner_member_id``），硬删会让归属列悬空，
    历史流水与账户失去主人。停用保留历史归属可追溯，且账户仍显示原归属。
    """
    member.is_active = False
    db.flush()
    db.refresh(member)
    ledger_count = (
        db.query(func.count(Ledger.id))
        .filter(Ledger.family_id == member.family_id, Ledger.owner_member_id == member.id)
        .scalar()
        or 0
    )
    return member_to_dict(member, ledger_count)


def get_member(db: Session, family_id: int, member_id: int) -> FamilyMember | None:
    """取家庭内的成员档案；不存在或跨家庭返回 ``None``（视图据此 404）。

    下沉到服务层是为了让**视图的 ORM 查询数不因新增端点而增长**——
    ``check_view_thickness.py`` 的 ``orm_queries`` 维度是「视图内直接查业务表」的计数，
    成员档案的查询属于业务规则，不该占视图的名额。
    """
    return db.query(FamilyMember).filter(FamilyMember.id == member_id, FamilyMember.family_id == family_id).first()


def member_name_map(db: Session, family_id: int) -> dict[int, str]:
    """家庭成员 ID → 称谓的映射（一次性取全量，供列表接口批量贴名字）。

    账户列表要显示「这笔钱是谁的」，但**不能在视图里逐个 join**——那会让
    ``check_view_thickness.py`` 的 ``orm_queries`` 维度增长（视图内直接查业务表
    是被守卫生效盯着的指标）。故取映射这件事放在服务层，视图只收一个 dict。
    """
    rows = db.query(FamilyMember.id, FamilyMember.name).filter(FamilyMember.family_id == family_id).all()
    return {row[0]: row[1] for row in rows}


def resolve_owner_member(db: Session, family_id: int, owner_member_id) -> int | None:
    """校验账户归属的成员是否合法，返回成员 ID（``None`` = 未归属/家庭共有）。

    校验点：成员存在、属同一家庭。**跨家庭归属一律拒绝**（否则能把别家成员挂到
    自家账户上，破坏家庭隔离）。停用的成员也允许**继续绑定已绑账户**（历史归属要留住），
    但新建账户时不该指派停用成员——那部分校验在写侧服务里做。
    """
    if owner_member_id is None:
        return None
    try:
        member_id = int(owner_member_id)
    except (TypeError, ValueError):
        raise FamilyMemberError('归属成员 ID 必须是整数', 400, 2004)

    member = db.query(FamilyMember).filter(FamilyMember.id == member_id, FamilyMember.family_id == family_id).first()
    if member is None:
        raise FamilyMemberError('归属成员不存在或不属于当前家庭', 400, 2005)
    return member.id


def ledger_ids_for_member(db: Session, family_id: int, member_id: int) -> list[int]:
    """某成员名下账户的 ID 列表——持仓按成员筛选时用它做 SQL 下推。"""
    rows = db.query(Ledger.id).filter(Ledger.family_id == family_id, Ledger.owner_member_id == member_id).all()
    return [r[0] for r in rows]

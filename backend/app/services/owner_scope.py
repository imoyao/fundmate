# -*- coding: utf-8 -*-
"""「归属成员 → 账户集合」的统一收口（#1173）。

WHY 单一出口
    按成员切片本质上都是同一件事：先由 `ledgers.owner_user_id` 求出该成员名下的
    `ledger_id` 集合，再把它下推到既有查询的账户过滤上（持仓列表、首页汇总、
    孤儿流水口径……）。若各处自行 `db.query(Ledger.id).filter(...)`，口径一变
    （例如将来允许「共享账户」多对多）就会出现「列表里两行、汇总只算一行」的分叉。

口径约定
    - **`family_id` 永远是第一道过滤**：`owner_user_id` 是家庭内切片，不是隔离维度，
      少了它就会把别的家庭同号成员的账户算进来（users.id 全局唯一，但防御性保留）；
    - 返回 ``None`` 表示「不按成员筛」（家庭全量），返回 ``[]`` 表示「该成员名下没有
      账户」——调用方必须把两者区分开：后者要返回空集，不能退化成全量。

边界
    本模块只做「成员 → ledger_id 集合」与「成员归属合法性校验」，不碰 HTTP，
    也不做聚合；聚合仍走 `summary_service.family_totals` 等既有唯一出口。
"""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.domains.ledgers.models import Ledger
from app.domains.users.models import User


def owner_ledger_ids(db: Session, family_id: int, owner_user_id: int) -> List[int]:
    """该成员在当前家庭名下的账户 id 列表（无账户返回 `[]`）。"""
    rows = (
        db.query(Ledger.id)
        .filter(
            Ledger.family_id == family_id,
            Ledger.owner_user_id == owner_user_id,
        )
        .all()
    )
    return [lid for (lid,) in rows]


def resolve_owner_ledger_ids(
    db: Session,
    family_id: int,
    owner_user_id: Optional[int],
) -> Optional[List[int]]:
    """成员过滤入参 → 账户 id 集合：`None` 原样返回（不筛），否则返回集合。"""
    if owner_user_id is None:
        return None
    return owner_ledger_ids(db, family_id, owner_user_id)


def is_family_member(db: Session, family_id: int, owner_user_id: int) -> bool:
    """`owner_user_id` 是否为当前家庭的成员（写入归属前必须校验，防跨家庭串人）。"""
    return (
        db.query(User.id)
        .filter(
            User.id == owner_user_id,
            User.family_id == family_id,
        )
        .first()
        is not None
    )


def owner_name_map(db: Session, owner_ids) -> dict[int, str]:
    """归属成员 id → 展示名（#1173），一次查询，调用方整页复用（避免 N+1）。

    展示名优先昵称，回退用户名，再回退裸 id（用户尚未填昵称时也不至于空白）。
    放在服务层而不是视图：视图不再持有 ORM 查询（`check_view_thickness` 判据）。
    """
    ids = {oid for oid in owner_ids if oid}
    if not ids:
        return {}
    rows = db.query(User.id, User.nickname, User.username).filter(User.id.in_(ids)).all()
    return {uid: (nickname or username or str(uid)) for uid, nickname, username in rows}

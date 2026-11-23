# -*- coding: utf-8 -*-
"""账户可见性判定（#3246 / D125 的唯一实现）.

为什么独立成模块而不写进 views：可见性是授权底座，判定必须**单点**。散落在 views 里的
``if ledger.visibility == ...`` 就是未来的越权入口——每加一个端点都要重写一遍，漏一个
就是洞。D125 已把三个轴切开，本模块只负责第三轴：

- 权限角色 ``users.role``：能做什么（全局写闸，viewer 只读）；
- 资产归属 ``owner_member_id``：这笔钱是谁的（**报表维度，不参与授权**）；
- 可见性 ``visibility``：谁能看见（本模块）。

判定规则（失败关闭）：

- ``shared`` ⇒ 同 family 内人人可见。存量行迁移后即此值，升级不掉数据；
- ``private`` 且 ``owner_user_id == 当前 user_id`` ⇒ 仅本人可见；
- ``private`` 且 ``owner_user_id IS NULL`` ⇒ **不可见**。正常路径由创建账户时服务端
  写入 owner，NULL 只可能来自裸 SQL；此时宁可少看见，不可多看见。

边界：本模块只回答「能不能看见」，不回答「能不能改」——写权限仍由 ``users.role``
（viewer 全局只读）把守。本卡范围内「可见即可写」。
"""

from sqlalchemy import and_, or_

from app.domains.ledgers.models import Ledger

VISIBILITY_PRIVATE = 'private'
VISIBILITY_SHARED = 'shared'
VISIBILITIES = (VISIBILITY_PRIVATE, VISIBILITY_SHARED)


def can_view(visibility, owner_user_id, user_id) -> bool:
    """单行判定（纯函数，便于单测；集合级过滤见 ``visible_ledger_ids``）."""
    if visibility == VISIBILITY_SHARED:
        return True
    return visibility == VISIBILITY_PRIVATE and owner_user_id is not None and owner_user_id == user_id


def _visible_clause(user_id):
    """可见性 WHERE 片段。``user_id`` 为空时只放行 shared——不能让
    ``owner_user_id == None`` 生成 ``IS NULL``，那会把 private 且无主账户放给匿名上下文。
    """
    if user_id is None:
        return Ledger.visibility == VISIBILITY_SHARED
    return or_(
        Ledger.visibility == VISIBILITY_SHARED,
        and_(Ledger.visibility == VISIBILITY_PRIVATE, Ledger.owner_user_id == user_id),
    )


def visible_ledger_ids(db, family_id: int, user_id) -> set[int]:
    """当前用户在该 family 内可见的账户 id 集合.

    查询层统一走它（``Ledger.id.in_(...)``）。**禁止**在 views 里直接比较
    ``ledger.visibility``——静态守卫 ``scripts/guard_ledger_visibility.py`` 会报红。
    """
    rows = db.query(Ledger.id).filter(Ledger.family_id == family_id, _visible_clause(user_id)).all()
    return {row.id for row in rows}

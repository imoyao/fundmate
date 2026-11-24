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


def restrict_visible(query, column, visible_ids):
    """把**账户可见性**条件挂到明细表（持仓 / 流水 / 资产）查询上；``None`` 原样返回.

    这是 ``can_view`` 判定在明细表上的第三种表述（前两种：单行 ``can_view``、
    集合 ``visible_ledger_ids``）。之所以不写成 ``column.in_(ids)`` 就完事——理由有两条：

    **1. NULL 不参与授权判定**。``ledger_id IS NULL`` 的明细（未归档持仓、未归档流水、
    导入暂存区）不归属任何账户，没有可判定的授权主体，按「无主＝家庭共有」放行，
    与 ``owner_member_id IS NULL`` 的语义同源。若按失败关闭隐藏它们，用户导入时还没
    分配账户的资产会凭空消失——那不是安全，是数据丢失。
    （2026-11-23 只读实测：active 且 ``ledger_id IS NULL`` 的持仓 0 条、
    ``ledger_id IS NULL`` 的流水 0 条 ⇒ 放行 NULL 在当前库上是零行为变化。）

    **2. 空集要显式处理**。``visible_ids`` 为空时只剩 NULL 行，用 ``column.is_(None)``
    而不是 ``or_(column.in_([]), ...)``——空 ``IN`` 在各方言下行为不一致（PG 直接语法错）。
    """
    if visible_ids is None:
        return query
    if not visible_ids:
        return query.filter(column.is_(None))
    return query.filter(or_(column.in_(visible_ids), column.is_(None)))

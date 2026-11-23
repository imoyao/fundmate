# -*- coding: utf-8 -*-
"""#3246 / D125：账户可见性判定（``visible_ledger_ids``）.

验收标准要求覆盖三种情形：

1. 同家庭 A 的 `private` 账户对 B 不可见；
2. `shared` 对 B 可见；
3. `owner_member_id` 与判定无关（改归属不影响可见性）。

另补三条边界，方向都是「失败关闭」：

4. `private` 但 `owner_user_id` 为空 ⇒ 谁都不见（防裸 SQL 写入变成放行）；
5. `user_id` 为空（未登录上下文）⇒ 只放行 shared，**不能**让
   `owner_user_id == None` 退化成 `IS NULL` 而匹配到无主私有账户；
6. 跨 family 不可见（可见性是 family 内的二次收敛，不是替代）。

为什么这些用例必须打真库：判定是一段 SQL 过滤。mock 掉 query 就测不到
``owner_user_id == None`` 生成 ``IS NULL`` 这类真实陷阱——那正是第 5 条要钉的。
"""

from app.domains.ledgers import visibility
from app.domains.ledgers.models import Ledger

OWNER = 11
OTHER = 22


def _ledger(db, name, *, vis, owner_user_id=None, owner_member_id=None, family_id=1):
    row = Ledger(
        name=name,
        ledger_type='stock',
        family_id=family_id,
        visibility=vis,
        owner_user_id=owner_user_id,
        owner_member_id=owner_member_id,
    )
    db.add(row)
    db.commit()
    return row


def test_private_visible_only_to_owner(db):
    mine = _ledger(db, '我的两融', vis=visibility.VISIBILITY_PRIVATE, owner_user_id=OWNER)

    assert visibility.visible_ledger_ids(db, 1, OWNER) == {mine.id}
    assert visibility.visible_ledger_ids(db, 1, OTHER) == set()


def test_shared_visible_to_everyone_in_family(db):
    shared = _ledger(db, '家庭现金', vis=visibility.VISIBILITY_SHARED, owner_user_id=OWNER)

    assert shared.id in visibility.visible_ledger_ids(db, 1, OWNER)
    assert shared.id in visibility.visible_ledger_ids(db, 1, OTHER)


def test_owner_member_id_does_not_grant_visibility(db):
    """D125：归属是报表维度、可见是授权维度。把 owner_member_id 指给 B 也不能让 B 看见.

    这条是整张卡的反向判据：如果哪天有人「顺手」用 owner_member_id 推可见性，
    这里会立刻红。
    """
    private = _ledger(db, '我的基金', vis=visibility.VISIBILITY_PRIVATE, owner_user_id=OWNER, owner_member_id=999)

    assert visibility.visible_ledger_ids(db, 1, OTHER) == set()
    assert visibility.visible_ledger_ids(db, 1, OWNER) == {private.id}


def test_private_without_owner_is_invisible(db):
    """失败关闭：private 且 owner 为空（只可能来自裸 SQL）不给任何人看."""
    _ledger(db, '无主私有', vis=visibility.VISIBILITY_PRIVATE)

    assert visibility.visible_ledger_ids(db, 1, OWNER) == set()
    assert visibility.visible_ledger_ids(db, 1, None) == set()


def test_anonymous_context_sees_only_shared(db):
    """user_id 为空时只放行 shared——防止 ``owner_user_id == None`` 生成 ``IS NULL``."""
    shared = _ledger(db, '家庭现金', vis=visibility.VISIBILITY_SHARED)
    _ledger(db, '无主私有', vis=visibility.VISIBILITY_PRIVATE)

    assert visibility.visible_ledger_ids(db, 1, None) == {shared.id}


def test_other_family_never_visible(db):
    _ledger(db, '别家共享账户', vis=visibility.VISIBILITY_SHARED, family_id=2)

    assert visibility.visible_ledger_ids(db, 1, OWNER) == set()


def test_can_view_pure_function():
    shared, private = visibility.VISIBILITY_SHARED, visibility.VISIBILITY_PRIVATE

    assert visibility.can_view(shared, None, None) is True
    assert visibility.can_view(private, OWNER, OWNER) is True
    assert visibility.can_view(private, OWNER, OTHER) is False
    assert visibility.can_view(private, None, OWNER) is False

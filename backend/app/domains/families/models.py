# -*- coding: utf-8 -*-
"""家庭模型（多用户家庭共享层，D1）与家庭成员档案（#1173）。

家庭是账本数据的归属容器：核心业务表按 `family_id` 归属家庭，成员共享同一套账本。
创建家庭时创建者自动成为该家庭主理人（admin）。

## 为什么成员档案要独立成表（#1173）

`users` 表是**登录账号**，不是「资产归属成员」：

- `users.supabase_id` 唯一且非空 —— 家庭成员（如「老婆」）很可能**没有 App 账号**，
  无法用 `users` 表达；硬塞就得给她造一个假 supabase_id；
- `users.role`（admin/member/viewer）是**权限角色**，「谁能改账本」与
  「这笔钱是谁的」是两件事，复用会让「角色」一词两义。

故新建 `family_members` 表承载**资产归属维度**：称谓、家庭内角色（户主/配偶/子女…）、
启用状态。`user_id` 字段（可空、无外键）用于把「有账号的成员」与登录账号挂上，
纯档案成员（无账号）留空即可。
"""

from sqlalchemy import Boolean, Column, Integer, String

from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin

# 家庭内角色词表——**故意不复用** users 的 admin/member/viewer（那是权限角色）。
MEMBER_ROLE_SELF = 'self'
MEMBER_ROLE_SPOUSE = 'spouse'
MEMBER_ROLE_CHILD = 'child'
MEMBER_ROLE_PARENT = 'parent'
MEMBER_ROLE_OTHER = 'other'

MEMBER_ROLE_LABELS = {
    MEMBER_ROLE_SELF: '本人',
    MEMBER_ROLE_SPOUSE: '配偶',
    MEMBER_ROLE_CHILD: '子女',
    MEMBER_ROLE_PARENT: '父母',
    MEMBER_ROLE_OTHER: '其他',
}

MEMBER_ROLES = tuple(MEMBER_ROLE_LABELS.keys())


class Family(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'families'

    name = Column(String(100), nullable=False, comment='家庭名称')


class FamilyMember(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """家庭成员档案（#1173）：账本账户的**归属人**。

    与 `users`（登录账号 / 权限角色）解耦：一个成员可以没有账号（纯档案），
    也可以通过 `user_id` 指向某个登录账号。
    """

    __tablename__ = 'family_members'

    name = Column(String(50), nullable=False, comment='成员称谓，如「老婆」')
    role = Column(
        String(20),
        default=MEMBER_ROLE_OTHER,
        comment='家庭内角色：self 本人 / spouse 配偶 / child 子女 / parent 父母 / other 其他'
        '（与 users.role 的权限语义无关）',
    )
    user_id = Column(
        Integer,
        nullable=True,
        comment='关联的登录账号 ID（可空：纯档案成员无账号）。无外键约束，SQLite 存量表无法 ALTER 加 FK，由应用层校验',
    )
    is_active = Column(Boolean, default=True, comment='是否启用（False=已停用，保留历史归属）')

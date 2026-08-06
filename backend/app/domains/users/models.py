# -*- coding: utf-8 -*-
"""用户模型（多用户身份层，D1/D2）。

本地 `users` 表是 Supabase Auth 用户在 SQLite 侧的映射：
- `supabase_id`：Supabase Auth 用户 UUID，登录后经 JWT claims.sub 关联；
- `family_id`：所属家庭（家庭共享层）；
- `role`：admin 主理人 / member 成员 / viewer 只读。
"""

from sqlalchemy import Column, ForeignKey, Integer, String

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin

# 角色常量（前端展示与权限判断共用）
ROLE_ADMIN = 'admin'
ROLE_MEMBER = 'member'
ROLE_VIEWER = 'viewer'
ROLE_LABELS = {
    ROLE_ADMIN: '主理人',
    ROLE_MEMBER: '成员',
    ROLE_VIEWER: '只读',
}


class User(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'users'

    supabase_id = Column(String(64), nullable=True, unique=True, comment='Supabase Auth 用户 UUID')
    family_id = Column(
        Integer,
        ForeignKey('families.id', ondelete='RESTRICT'),
        nullable=False,
        default=1,
        comment='所属家庭 ID',
    )
    username = Column(String(100), nullable=True, comment='用户名（默认取邮箱前缀）')
    nickname = Column(String(100), nullable=True, comment='昵称（个人中心可编辑）')
    avatar = Column(String(500), nullable=True, comment='头像 URL')
    email = Column(String(200), nullable=True, comment='邮箱')
    role = Column(String(20), default=ROLE_MEMBER, comment='admin/member/viewer')
    is_active = Column(Integer, default=1, comment='是否启用（0 停用）')

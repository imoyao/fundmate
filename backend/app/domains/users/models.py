# -*- coding: utf-8 -*-
"""用户模型（多用户身份层，D1/D2）。

本地 `users` 表是 Supabase Auth 用户在 SQLite 侧的映射：
- `supabase_id`：Supabase Auth 用户 UUID，登录后经 JWT claims.sub 关联；
- `family_id`：所属家庭（家庭共享层）；
- `role`：admin 主理人 / member 成员 / viewer 只读。
"""

from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func

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

    # 登录标识（username）必须**大小写不敏感唯一**（D10 / #2764）。
    #
    # 为什么不能只靠应用层 409：`update_me` 与 `provision` 是两条写入路径，
    # 任何一条漏判就会落下 `devyao` 与 `Devyao` 两行；而 `resolve_identifier`
    # 按 `lower(username)` 匹配、取 id 最小那条，于是**后注册的人会把先注册的人
    # 顶掉**（登录解析到别人的邮箱，原主从此用用户名登不进去）。
    # 判据必须下沉到库：应用层判重只是「给人看的提示」，唯一索引才是兜底。
    #
    # 用表达式索引而非列级 `unique=True`：SQLite 与 Postgres 都支持
    # `lower(col)` 索引；`username` 可空，两边都允许多个 NULL，不影响种子/测试用户。
    __table_args__ = (Index('uq_users_username_lower', func.lower(username), unique=True),)


class UserPreference(Base, PrimaryKeyMixin, TimestampMixin):
    """用户私有偏好键值存储（#1337，#993 方案 B 跨设备同步）。

    - `user_id` 私有（非 family_id）：列配置这类偏好属于个人，不随家庭共享；
    - `key` 唯一约束 (user_id, key)：同一偏好一行，写入走 upsert；
    - `value` 存 JSON 文本：偏好结构演进频繁（如 hidden/shown/order），
      不为每个字段开列；updated_at 由 TimestampMixin 维护，供前端「最近修改
      时间取胜」的合并策略读取。
    """

    __tablename__ = 'user_preferences'
    __table_args__ = (UniqueConstraint('user_id', 'key', name='uq_user_prefs_user_key'),)

    user_id = Column(
        Integer,
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='归属用户',
    )
    key = Column(String(100), nullable=False, comment='偏好键（如 watchlist-column-settings）')
    value = Column(Text, nullable=False, comment='偏好值（JSON 文本）')

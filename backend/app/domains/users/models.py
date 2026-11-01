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


class AuthAuditLog(Base, PrimaryKeyMixin, TimestampMixin):
    """身份类事件的审计台账（D76 / #2780，user 域）。

    **为什么单独一张表、不复用 `sync_logs`**：那是市场同步任务的流水（market 域），
    与身份事件的数据域、写方、保留期都不同；混在一起会让「查某用户被改过几次邮箱」
    变成一次跨域扫描。

    **写入方有两个，刻意不合并**：

    - ``source='supabase'``：Supabase 侧 `auth.users` 的 `AFTER UPDATE` 触发器写入
      （执行清单与 DDL 见 `docs/dev/auth-audit.md`）。这是**邮箱 / 密码变更唯一
      可见的地方**——那条链路走前端直连 GoTrue，不经过本仓后端；
    - ``source='backend'``：本仓认证端点（resolve / logout / 资料变更）的请求流水。

    **不建外键，两个理由**：① resolve 未命中时还没有 `user_id`；② 审计不得随
    `users` 行删除而级联消失——恰恰是「用户被删前发生了什么」最需要留痕。归因用
    `user_id` + `supabase_id` 双键，后者在 JIT 建号之前也能对上 Supabase Auth 用户。

    **禁止写入**：密码、refresh token、邮箱明文（只存打码 / 哈希形式）。
    """

    __tablename__ = 'auth_audit'
    __table_args__ = (
        Index('ix_auth_audit_user_created', 'user_id', 'created_at'),
        Index('ix_auth_audit_event_created', 'event', 'created_at'),
        Index('ix_auth_audit_supabase_created', 'supabase_id', 'created_at'),
    )

    user_id = Column(Integer, nullable=True, comment='users.id（可为空：未登录事件）')
    supabase_id = Column(String(64), nullable=True, comment='Supabase Auth UUID（兼容尚未 JIT 建号的用户）')
    event = Column(String(40), nullable=False, comment='auth.email.changed / auth.resolve.miss …')
    source = Column(
        String(20),
        nullable=False,
        default='backend',
        comment='backend=本仓请求流水；supabase=auth.users 触发器',
    )
    identifier = Column(String(200), nullable=True, comment='脱敏后的登录标识')
    ip = Column(String(64), nullable=True, comment='截断后的来源 IP')
    user_agent = Column(String(200), nullable=True, comment='截断后的 UA')
    detail = Column(Text, nullable=True, comment='JSON 明细；禁止密码 / refresh token / 邮箱明文')

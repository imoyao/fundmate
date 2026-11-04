# -*- coding: utf-8 -*-
"""用户身份读写实现（#1607：core 不得反向依赖领域层的注入点）。

`app/core/auth.py` 是鉴权中间件，属业务无关的基础设施层。按 `decisions.md` 确立的依赖方向
（core ← domains ← services），core **不得** import 领域模型，因此「按 id / supabase_id 查用户」
「首次登录 JIT 建号」「回写最新邮箱」这些必须用到 `User` 模型的读写全部下沉到本模块，
由组合根（`app/main.py` 的 `create_app`）注入 `core.auth`；core 侧只持有实现对象并调用下面的
鸭子类型接口，注入前完全不感知 `User`（未注入时显式报错，不静默降级）。

core.auth 依赖的接口（改动这里等于改 core 侧契约，须两边同步）：
- ``get_by_id(db, user_id)``              → ``User | None``
- ``get_by_supabase_id(db, supabase_id)`` → ``User | None``
- ``provision(db, claims)``               → ``User``（幂等，并发首次登录回查已建行）
- ``sync_email(db, user, claims)``        → ``None``
"""

from uuid import uuid4

from loguru import logger
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.domains.users.models import ROLE_MEMBER, User


class UserIdentity:
    """基于 SQLAlchemy `users` 表的身份读写实现（纯静态方法、无状态）。"""

    @staticmethod
    def get_by_id(db, user_id: int):
        """按本地主键取用户（X-User-Id 测试旁路、无鉴权模式回退默认用户用）。"""
        return db.query(User).filter_by(id=user_id).first()

    @staticmethod
    def get_by_supabase_id(db, supabase_id: str):
        """按 Supabase Auth 用户 UUID（JWT 的 claims.sub）取本地映射行。"""
        return db.query(User).filter_by(supabase_id=supabase_id).first()

    @staticmethod
    def _available_username(db, desired: str) -> str:
        """在「大小写不敏感」口径下取一个尚未占用的用户名（撞名追加 `_2` / `_3`…）。

        为什么必须做：`users.username` 是登录标识且现在有唯一索引（#2764）。
        provision 是**第三条**写入路径（另外两条是注册与个人中心改名），它拿到的
        候选名来自 `user_metadata.username` 或邮箱前缀——两者都可能与已有用户撞车
        （同邮箱前缀、或注册时填了别人的名字）。撞车若直接落库，要么 500，
        要么退化成「静默重名 + resolve 取 id 最小」，等于把一个人顶掉。

        为什么不报错让用户重填：JIT 建号发生在「已通过 Supabase 验签的请求」里，
        此刻没有表单可回填；能做的只有换一个可用名并留日志（用户可在个人中心改）。
        """
        base = (desired or '').strip() or 'user'
        # username 列宽 100，预留后缀空间；超长时截断而不是让 INSERT 失败
        if len(base) > 90:
            base = base[:90]
        candidate = base
        for suffix in range(2, 52):
            taken = db.query(User.id).filter(func.lower(User.username) == candidate.lower()).first()
            if taken is None:
                return candidate
            candidate = f'{base}_{suffix}'
        # 极端情况（连续 50 个都占用）：退回随机后缀，保证不撞唯一索引
        return f'{base}_{uuid4().hex[:8]}'

    @staticmethod
    def provision(db, claims: dict):
        """首次登录自动创建本地用户（JIT provisioning）。

        Supabase 是云端权威（D3），但本地 `users` 表是 SQLite 侧的映射：
        新用户在 Supabase 注册后，本地并无对应记录。这里在 JWT 验签成功、
        且 `claims.sub` 查无此人时，用 claims 中的身份信息自动建号，
        否则新用户将永远 401，无法使用任何受保护功能。

        角色默认 member（普通成员），归属默认家庭 1，后续可经家庭管理调整。

        用户名：候选名撞车时由 :meth:`_available_username` 追加后缀（#2764）。
        不这样做的话，两个邮箱前缀相同的用户会落下同名两行，而 `resolve_identifier`
        按 lower(username) 取 id 最小那条 ⇒ 后注册的人永远登不进去。
        """
        sub = claims.get('sub')
        email = claims.get('email') or ''
        user_metadata = claims.get('user_metadata') or {}
        base_username = user_metadata.get('username') or email.split('@')[0] or f'user_{sub[:8]}'
        username = UserIdentity._available_username(db, base_username)
        if username != base_username:
            logger.warning('首次登录建号：用户名 {} 已被占用，改用 {}（sub={}）', base_username, username, sub)

        for _attempt in range(3):
            user = User(
                supabase_id=sub,
                family_id=1,
                username=username,
                nickname=username,
                email=email,
                role=ROLE_MEMBER,
                is_active=1,
            )
            db.add(user)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                # 并发首次登录：另一请求已按同一个 sub 抢建，回查即可
                existing = db.query(User).filter_by(supabase_id=sub).first()
                if existing is not None:
                    logger.info('首次登录建号并发命中：回查已建行 sub={}', sub)
                    return existing
                # 否则撞的是 username 唯一索引（并发抢注同名）——换名重试
                username = UserIdentity._available_username(db, base_username)
                logger.warning('首次登录建号撞名，改用 {} 重试（sub={}）', username, sub)
                continue
            db.refresh(user)
            logger.info('首次登录自动创建本地用户 sub={} username={}', sub, username)
            return user

        raise RuntimeError(f'首次登录建号失败：sub={sub} 连续撞名（用户名唯一索引）')

    @staticmethod
    def sync_email(db, user, claims: dict):
        """把 Supabase 侧最新的邮箱回写本地 `users.email`。

        用户改绑邮箱（D10，前端经 `supabase.auth.updateUser({email})` 触发二次验证）
        后，Supabase 是新邮箱的权威，而本地 `users` 只是映射。若这里的
        `claims.email` 与本地不一致，则同步，避免"个人中心仍显示旧邮箱"的陈旧数据。
        """
        claims_email = (claims.get('email') or '').strip()
        if claims_email and user.email != claims_email:
            user.email = claims_email
            db.commit()
            logger.info('同步 Supabase 最新邮箱到本地 sub={}', claims.get('sub'))

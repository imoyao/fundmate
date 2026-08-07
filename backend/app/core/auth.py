# -*- coding: utf-8 -*-
"""身份鉴权核心（D2：后端为唯一信任边界）。

- 每个受保护请求带 `Authorization: Bearer <supabase access_token>`，
  后端用 `SUPABASE_JWT_SECRET` + PyJWT 本地验签（不发网络请求），
  从 `claims.sub` 映射本地 `users` 表，注入 `g.current_user / family_id / role`。
- 白名单：health、temperature（探市免登录，D4）、auth/logout、OPTIONS 预检。
- 开发/测试模式（`AUTH_ENABLED` 未启用）：允许无 token 回退默认用户，
  支持 `X-User-Id` 头旁路指定身份（仅测试用）。
- viewer（只读）角色对写方法统一 403（单一拦截点，避免逐端点装饰遗漏）。
"""

import os
from functools import wraps

from flask import abort, g, request
from loguru import logger
from sqlalchemy.exc import IntegrityError

# 免登录前缀：探市相关接口（含无尾斜杠的 /api/temperature/{overview,history,multi}）
PUBLIC_PREFIXES = ('/api/health', '/api/temperature')
# 免登录精确路径
# - logout：允许无有效 token 也返回成功（由前端清理本地会话）
# - auth/resolve：登录前的"标识→邮箱"解析，帮助 Supabase 完成用户名登录（D10）
PUBLIC_EXACT = (
    '/api/auth/logout',
    '/api/auth/resolve',
)

_WRITE_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')


def _is_public(path: str, method: str) -> bool:
    """判断请求是否属于免登录白名单（D4：探市免登录）。"""
    if method == 'OPTIONS':
        # CORS 预检请求必须放行，否则跨域写请求会被拦截
        return True
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def auth_enabled() -> bool:
    """是否强制启用登录门禁（生产开、开发/测试默认关）。"""
    return os.getenv('AUTH_ENABLED', '').strip().lower() in ('1', 'true', 'yes')


def decode_supabase_token(token: str) -> dict | None:
    """本地验签 Supabase access_token，返回 claims；无效返回 None。"""
    jwt_secret = os.getenv('SUPABASE_JWT_SECRET')
    if not jwt_secret:
        logger.debug('未配置 SUPABASE_JWT_SECRET，跳过 JWT 验签')
        return None
    try:
        import jwt  # PyJWT，延迟导入以保持依赖轻量
    except ImportError:  # pragma: no cover
        logger.error('缺少 PyJWT 依赖，无法验签 Supabase token')
        return None
    try:
        return jwt.decode(token, jwt_secret, algorithms=['HS256'])
    except Exception:
        logger.debug('Supabase token 验签失败')
        return None


def _provision_user(db, claims: dict):
    """首次登录自动创建本地用户（JIT provisioning）。

    Supabase 是云端权威（D3），但本地 `users` 表是 SQLite 侧的映射：
    新用户在 Supabase 注册后，本地并无对应记录。这里在 JWT 验签成功、
    且 `claims.sub` 查无此人时，用 claims 中的身份信息自动建号，
    否则新用户将永远 401，无法使用任何受保护功能。

    角色默认 member（普通成员），归属默认家庭 1，后续可经家庭管理调整。
    """
    from app.domains.users.models import ROLE_MEMBER, User

    sub = claims.get('sub')
    email = claims.get('email') or ''
    user_metadata = claims.get('user_metadata') or {}
    username = user_metadata.get('username') or email.split('@')[0] or f'user_{sub[:8]}'

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
        # 并发首次登录：另一请求已抢建，回查即可
        db.rollback()
        user = db.query(User).filter_by(supabase_id=sub).first()
        if user is None:
            raise
    db.refresh(user)
    logger.info('首次登录自动创建本地用户 sub={} username={}', sub, username)
    return user


def _sync_claims_email(db, user, claims: dict):
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


def _resolve_user(db):
    """从请求上下文解析本地用户（优先测试旁路头，其次 JWT 验签）。"""
    # 测试/开发旁路：X-User-Id 头直接指定本地用户 id
    xid = request.headers.get('X-User-Id')
    if xid:
        try:
            from app.domains.users.models import User

            return db.query(User).filter_by(id=int(xid)).first()
        except ValueError:
            return None

    auth_header = request.headers.get('Authorization', '')
    token = auth_header[7:].strip() if auth_header.lower().startswith('bearer ') else ''
    if not token:
        return None

    claims = decode_supabase_token(token)
    if not claims:
        return None
    sub = claims.get('sub')
    if not sub:
        return None
    from app.domains.users.models import User

    user = db.query(User).filter_by(supabase_id=sub).first()
    if user is None:
        user = _provision_user(db, claims)
    else:
        _sync_claims_email(db, user, claims)
    return user


def auth_before_request():
    """全局鉴权中间件（挂载于 create_app）。"""
    if _is_public(request.path, request.method):
        return None

    from app.core.database import SessionLocal  # 延迟导入，确保测试 monkeypatch 生效

    db = SessionLocal()
    try:
        user = _resolve_user(db)
        if user is None and not auth_enabled():
            # 开发/未启用模式：回退默认用户，保持本地单用户可用
            from app.domains.users.models import User

            user = db.query(User).filter_by(id=1).first()

        if user is None:
            abort(401, description='未授权，请先登录')

        g.current_user = user
        g.family_id = user.family_id
        g.role = user.role

        # viewer 只读分权（D1）：对写方法统一 403
        if user.role == 'viewer' and request.method in _WRITE_METHODS:
            abort(403, description='只读用户无写入权限')
        return None
    finally:
        db.close()


def get_family_id() -> int:
    """当前请求归属家庭 ID（未鉴权/单用户时默认 1）。"""
    return getattr(g, 'family_id', 1)


def get_owned_or_404(db, model, obj_id: int):
    """按 family 作用域取家庭内资源，越权或不存在统一 404（避免泄露存在性）。

    要求 model 为 FamilyScopedMixin（含 family_id 列）。
    """
    obj = db.query(model).filter(model.id == obj_id, model.family_id == get_family_id()).first()
    if not obj:
        abort(404, description='资源不存在或无权访问')
    return obj


def get_role() -> str:
    """当前请求用户角色（未鉴权时默认 member）。"""
    return getattr(g, 'role', 'member')


def require_roles(*roles: str):
    """角色守卫装饰器：仅允许指定角色访问（如 require_roles('admin')）。"""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if get_role() not in roles:
                abort(403, description='没有权限执行此操作')
            return fn(*args, **kwargs)

        return wrapper

    return decorator

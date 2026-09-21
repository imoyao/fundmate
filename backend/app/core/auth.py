# -*- coding: utf-8 -*-
"""身份鉴权核心（D2：后端为唯一信任边界）。

- 每个受保护请求带 `Authorization: Bearer <supabase access_token>`，
  后端从 Supabase JWKS 端点获取公钥，用 ES256 验签（非对称，支持密钥轮换），
  从 `claims.sub` 映射本地 `users` 表，注入 `g.current_user / family_id / role`。
- 白名单：health、temperature（探市市场温度，D4）、securities/search 与 funds/search（探市页免登录搜索候选标的，D4 延伸，均为 GET 只读公开查询）、auth/logout、auth/resolve、OPTIONS 预检。
- 开发/测试模式（`AUTH_ENABLED` 未启用）：允许无 token 回退默认用户，
  支持 `X-User-Id` 头旁路指定身份（仅测试用）。
- viewer（只读）角色对写方法统一 403（单一拦截点，避免逐端点装饰遗漏）。
- 用户身份读写经**注入**获得（#1607）：本模块属业务无关的基础设施层，按 `decisions.md`
  的依赖方向（core ← domains ← services）不得 import 领域模型，查用户 / 建号 / 回写邮箱
  下沉在 `app.domains.users.identity`，由组合根 `create_app()` 调用 `register_user_identity()`
  注入；未注入即报错，不静默降级（否则鉴权会悄悄失效）。
"""

import os
import threading
import time
from functools import wraps

from flask import abort, g, request
from loguru import logger

# 免登录前缀（_is_public 用 startswith 匹配，故前缀须精确到「子路由」层级，
# 不能只到 /api/funds 这种蓝图级，否则会误放行同蓝图下的写接口，如 /api/funds/nav）。
# - /api/health、/api/temperature：探市市场温度（D4 免登录）
# - /api/securities/search、/api/funds/search：探市页「添加资产」的免登录搜索框依赖，
#   前端 useAssetSearch 据此拉取候选标的。二者均为 GET 只读公开数据（基金/证券名录），
#   无写操作，加白名单不影响数据安全。修复 #821 P0-1：原白名单缺失该两项，导致生产
#   AUTH_ENABLED=true 时匿名访客搜索必 401，且被前端 Promise.allSettled+catch 静默吞掉，
#   核心交互（添加资产）实际不可用。
# - /api/utils/config：平台级实时估值总闸（issue #826）。探市页 /explore 免登录也使用
#   实时估值（useRealtimeQuotes），匿名访客必须能读到平台级开关，否则生产
#   AUTH_ENABLED=true 时匿名用户拿不到总闸。前缀精确到 /api/utils/config（子路由层级），
#   不能只到 /api/utils，避免误放行同蓝图下其他接口（如 /api/utils/trading-days/）。
# - /api/utils/enums：下发枚举中文标签（如持仓来源）。前端展示「来源徽标」用，探市页
#   免登录也展示来源，故免登录。标签真相源在 app.core.constants，前端不手抄第二份。
PUBLIC_PREFIXES = (
    '/api/health',
    '/api/temperature',
    '/api/securities/search',
    '/api/funds/search',
    '/api/utils/config',
    '/api/utils/enums',
)
# 免登录精确路径
# - logout：允许无有效 token 也返回成功（由前端清理本地会话）
# - auth/resolve：登录前的"标识→邮箱"解析，帮助 Supabase 完成用户名登录（D10）
PUBLIC_EXACT = (
    '/api/auth/logout',
    '/api/auth/resolve',
)

_WRITE_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')

# JWKS 缓存：{kid: {'key': public_key, 'exp': timestamp}}
_JWKS_CACHE = {}
_JWKS_CACHE_LOCK = threading.Lock()
_JWKS_TTL = 3600  # 1 小时


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


# 用户身份读写实现（#1607）：core 不 import 领域模型，由组合根注入。
# 实现须提供 get_by_id / get_by_supabase_id / provision / sync_email 四个接口，
# 见 `app/domains/users/identity.py` 的模块 docstring。
_user_identity = None


def register_user_identity(identity) -> None:
    """注入用户身份读写实现（由 `app/main.py` 的 `create_app()` 调用）。

    为什么是注入而不是直接 import：`User` 是领域模型，core 依赖 domains 会让基础设施层
    无法脱离领域层导入与测试（#1607）。这里只持有实现对象，签名与语义由注入方保证。
    """
    global _user_identity
    _user_identity = identity


def _identity():
    """取已注入的身份实现；未注入即报错。

    刻意不返回 None 后静默跳过：鉴权链路上任何「静默降级」都会变成安全缺口
    （如误判为未登录而放行，或误判为已登录而越权），宁可 500 暴露配置错误。
    """
    if _user_identity is None:
        raise RuntimeError('用户身份实现未注入：请在 create_app() 中调用 register_user_identity()（#1607）')
    return _user_identity


def _fetch_jwks(supabase_url: str) -> dict:
    """从 Supabase 获取 JWKS 公钥集合。

    端点是 `/auth/v1/.well-known/jwks.json`（OpenID Discovery 里的 `jwks_uri`，
    而非 `/auth/v1/jwks`，后者会 404）；GoTrue 网关要求 `apikey` 头（用 anon key 即可）。
    实测（2026-08-08）返回两条 ES256 P-256 公钥，kid 与 Dashboard「JWT Signing Keys」
    的 Current / Standby 一一对应，做 ES256 非对称验签，天然支持密钥轮换。
    """
    import requests

    anon_key = os.getenv('SUPABASE_ANON_KEY', '')
    jwks_url = f'{supabase_url.rstrip("/")}/auth/v1/.well-known/jwks.json'
    headers = {'apikey': anon_key, 'Authorization': f'Bearer {anon_key}'}
    resp = requests.get(jwks_url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_public_key(supabase_url: str, kid: str):
    """从 JWKS 获取指定 kid 的公钥（带缓存）。"""
    now = time.time()
    with _JWKS_CACHE_LOCK:
        # 清理过期缓存
        expired = [k for k, v in _JWKS_CACHE.items() if v['exp'] < now]
        for k in expired:
            _JWKS_CACHE.pop(k, None)

        cached = _JWKS_CACHE.get(kid)
        if cached and cached['exp'] > now:
            return cached['key']

        # 缓存未命中或过期，重新拉取
        jwks = _fetch_jwks(supabase_url)
        for jwk in jwks.get('keys', []):
            if jwk.get('kid') == kid:
                import jwt

                # PyJWT 2.0+ 支持直接用 jwk dict
                public_key = jwt.algorithms.ECAlgorithm.from_jwk(jwk)
                _JWKS_CACHE[kid] = {'key': public_key, 'exp': now + _JWKS_TTL}
                return public_key

    return None


def decode_supabase_token(token: str) -> dict | None:
    """验签 Supabase access_token（ES256 + JWKS），返回 claims；无效返回 None。"""
    supabase_url = os.getenv('SUPABASE_URL')
    if not supabase_url:
        logger.debug('未配置 SUPABASE_URL，跳过 JWT 验签')
        return None

    try:
        import jwt
    except ImportError:  # pragma: no cover
        logger.error('缺少 PyJWT 依赖，无法验签 Supabase token')
        return None

    # 解析 header 获取 kid（不验签）
    try:
        header = jwt.get_unverified_header(token)
    except Exception as e:
        logger.debug('JWT header 解析失败: {}', e)
        return None

    kid = header.get('kid')
    if not kid:
        logger.debug('JWT header 缺少 kid')
        return None

    public_key = _get_public_key(supabase_url, kid)
    if public_key is None:
        logger.debug('JWKS 中未找到 kid={} 对应的公钥', kid)
        return None

    try:
        # Supabase 现在用 ES256 (ECDSA P-256)
        return jwt.decode(token, public_key, algorithms=['ES256'], audience='authenticated')
    except Exception as e:
        logger.debug('Supabase token 验签失败: {}', e)
        return None


def _resolve_user(db):
    """从请求上下文解析本地用户（优先测试旁路头，其次 JWT 验签）。

    查用户 / 首次登录建号 / 邮箱回写均委托注入的身份实现（#1607），
    本模块不持有 `User` 模型。
    """
    identity = _identity()

    # 测试/开发旁路：X-User-Id 头直接指定本地用户 id
    xid = request.headers.get('X-User-Id')
    if xid:
        try:
            return identity.get_by_id(db, int(xid))
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

    user = identity.get_by_supabase_id(db, sub)
    if user is None:
        user = identity.provision(db, claims)
    else:
        identity.sync_email(db, user, claims)
    return user


def auth_before_request():
    """全局鉴权中间件（挂载于 create_app）。"""
    if _is_public(request.path, request.method):
        return None

    from app.core.database import get_session  # 延迟导入，确保测试 monkeypatch 生效

    db = get_session()
    try:
        user = _resolve_user(db)
        if user is None and not auth_enabled():
            # 开发/未启用模式：回退默认用户 1（由 domains.users.seed 播种），保持本地单用户可用
            user = _identity().get_by_id(db, 1)

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

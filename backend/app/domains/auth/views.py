# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/1
# File : views.py
# 认证模块 API（退出登录统一入口）

from apiflask import APIBlueprint
from flask import g, request
from loguru import logger
from pydantic import BaseModel

from app.core import supabase_admin
from app.core.exceptions import ErrorCode, SBException
from app.domains.families.models import Family
from app.domains.users.models import ROLE_LABELS, User

auth_bp = APIBlueprint('auth', __name__, url_prefix='/api/auth')

#: `resolve` 的单来源限流（次 / 分钟 / 进程）。见 `app/core/ratelimit.py` 的能力边界说明。
RESOLVE_RATE_LIMIT_PER_MINUTE = 20


def _client_ip() -> str:
    """取调用方 IP 作为限流键。

    优先 `X-Forwarded-For` 第一跳：后端实际部署在反向代理（容器平台）后面时，
    `remote_addr` 是**代理**的地址，全站共用一个桶会把正常用户一起卡死。
    代价是伪造该头即可绕过限流——但绕过限流只是「枚举得更快」，不扩大数据暴露面，
    比「所有人共享配额」可接受得多。若将来配了 `ProxyFix`，这里应改回 `remote_addr`。
    """
    forwarded = (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
    return forwarded or (request.remote_addr or 'unknown')


class ResolveRequest(BaseModel):
    identifier: str


@auth_bp.post('/resolve/', strict_slashes=False)
def resolve_identifier():
    """登录标识解析（D10）：把「邮箱 或 用户名」收敛为规范邮箱，供前端二次登录。

    本接口免登录（PUBLIC_EXACT）——登录前必须能调用它。解析口径（大小写不敏感 /
    用户名歧义 409 / 不存在 404 且不泄露邮箱）在 `app/services/login_identifier.py`，
    这里只做限流与 HTTP 编排。

    限流（#2764）：免登录 + 返回规范邮箱，等于把「用户名 ↔ 邮箱」映射开放给任何脚本
    枚举，故按来源 IP 每分钟 20 次，超限 429（`RATE_LIMIT_EXCEEDED`）。
    """
    from app.core import ratelimit  # 调用期解析，便于测试替换
    from app.core.database import get_db  # 延迟导入，与测试 monkeypatch 对齐
    from app.core.validation import parse_body
    from app.services.login_identifier import resolve_login_identifier

    ip = _client_ip()
    if not ratelimit.check(f'resolve:{ip}', limit=RESOLVE_RATE_LIMIT_PER_MINUTE):
        logger.warning('resolve 限流触发：ip={}', ip)
        raise SBException(
            code=ErrorCode.RATE_LIMIT_EXCEEDED.code,
            message=ErrorCode.RATE_LIMIT_EXCEEDED.msg,
            status_code=ErrorCode.RATE_LIMIT_EXCEEDED.http_status,
        )

    data = parse_body(ResolveRequest)
    with get_db() as db:
        email = resolve_login_identifier(db, data.identifier)
    return {'data': {'email': email}, 'message': 'ok'}


@auth_bp.get('/me/', strict_slashes=False)
def me():
    """返回当前登录用户信息（含角色与所属家庭）。

    依赖鉴权中间件已注入 `g.current_user`；未登录访问本接口由中间件返回 401。
    """
    from app.core.database import get_db

    user: User = g.current_user
    family_name = None
    with get_db() as db:
        fam = db.query(Family).filter_by(id=user.family_id).first()
        family_name = fam.name if fam else None

    return {
        'data': {
            'id': user.id,
            'supabase_id': user.supabase_id,
            'username': user.username,
            'nickname': user.nickname,
            'avatar': user.avatar,
            'email': user.email,
            'role': user.role,
            'role_label': ROLE_LABELS.get(user.role, user.role),
            'family': {'id': user.family_id, 'name': family_name},
        },
        'message': 'ok',
    }


@auth_bp.post('/logout/', strict_slashes=False)
def logout():
    """退出登录。

    前端退出时统一调用本接口，并把当前 Supabase 的 access_token 通过 Authorization
    头带上来。服务端作废会话的 Admin API 调用收口在 `app/core/supabase_admin.py`
    （#2764）：凭证只在那一处出现，「作废失败不阻断退出」的语义也在那里统一实现。
    未配置凭证时仅返回成功，由前端清理本地 token 完成退出。
    """
    auth_header = request.headers.get('Authorization', '')
    user_token = auth_header[7:].strip() if auth_header.lower().startswith('bearer ') else ''
    if user_token:
        supabase_admin.revoke_session(user_token)
    return {'success': True, 'message': '已退出登录'}

# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/1
# File : views.py
# 认证模块 API（退出登录统一入口）

from apiflask import APIBlueprint
from flask import abort, g, request
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func

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
    """登录标识解析（D10）：把"邮箱 或 用户名"收敛为规范邮箱，供前端二次登录。

    Supabase Auth 原生仅支持 "邮箱/手机号 + 密码" 登录，不支持用户名登录。
    这里作为解析层：前端拿到用户输入（可能是邮箱或用户名）后，先调用本接口，
    由本地 `users` 表把标识解析为规范 email，再交给 `signInWithPassword`。

    解析优先级：
    1. 若输入形如邮箱（含 `@`），先按 `email` 精确匹配；
    2. 否则按 `username`（不区分大小写）匹配；
    3. 仍无匹配 → 404，表示该标识不存在（不泄露任何邮箱信息）。

    **歧义不静默**（#2764）：用户名命中多行时返回 409，而不是取 id 最小那条。
    旧行为把「同一用户名指向两个账号」这件事藏了起来——被顶掉的那个人只会看到
    「密码错误」，永远查不到原因。邮箱命中多行则按 id 最小解析并打 WARNING：
    同一个邮箱无论取哪行，最终登录的都是同一个 Supabase 账号，不存在顶号。

    大小写口径：邮箱与用户名都按 `lower()` 匹配。Supabase 侧邮箱一律小写，
    本地可能留着注册时的原始大小写，按字面量比较会 404（同一份数据两种口径）。

    本接口免登录（PUBLIC_EXACT），因为登录前必须能调用它。

    限流（#2764 遗留项）：按来源 IP 每分钟 20 次。免登录 + 返回规范邮箱，等于把
    「用户名 ↔ 邮箱」映射开放给任何脚本枚举——不限流就是一条现成的采集通道。
    超限返回 429（`RATE_LIMIT_EXCEEDED`），前端按「稍后再试」处理。
    """
    from app.core import ratelimit  # 调用期解析，便于测试替换
    from app.core.database import get_db  # 延迟导入，与测试 monkeypatch 对齐
    from app.core.validation import parse_body

    if not ratelimit.check(f'resolve:{_client_ip()}', limit=RESOLVE_RATE_LIMIT_PER_MINUTE):
        logger.warning('resolve 限流触发：ip={}', _client_ip())
        raise SBException(
            code=ErrorCode.RATE_LIMIT_EXCEEDED.code,
            message=ErrorCode.RATE_LIMIT_EXCEEDED.msg,
            status_code=ErrorCode.RATE_LIMIT_EXCEEDED.http_status,
        )

    data = parse_body(ResolveRequest)
    identifier = data.identifier.strip()
    if not identifier:
        abort(400, description='登录标识不能为空')

    is_email = '@' in identifier
    with get_db() as db:
        if is_email:
            users = db.query(User).filter(func.lower(User.email) == identifier.lower()).order_by(User.id.asc()).all()
        else:
            users = db.query(User).filter(func.lower(User.username) == identifier.lower()).order_by(User.id.asc()).all()
        if not users:
            abort(404, description='未找到该邮箱或用户名，请检查后重试')
        if len(users) > 1 and not is_email:
            logger.warning(
                '登录标识歧义：username={} 命中 {} 行（id={}），拒绝解析（#2764）',
                identifier,
                len(users),
                [u.id for u in users],
            )
            abort(409, description='该用户名对应多个账号，请改用邮箱登录')
        if len(users) > 1:
            logger.warning(
                '同一邮箱命中多行（id={}），按 id 最小解析；建议清理跨项目幽灵行（#2764）',
                [u.id for u in users],
            )
        return {'data': {'email': users[0].email}, 'message': 'ok'}


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

    前端退出时统一调用本接口，并把当前 Supabase 的 access_token 通过
    Authorization 头带上来。若后端配置了 SUPABASE_URL 与
    SUPABASE_SERVICE_ROLE_KEY，则调用 Supabase Admin API 在**服务端**作废
    该会话（避免前端直接暴露认证请求、也保证 token 真正失效）；否则仅返回
    成功，由前端清理本地 token 完成退出。

    这样无论是否接入 Supabase 管理服务，退出链路都统一收敛到后端入口。

    Admin API 调用已收口到 `app/core/supabase_admin.py`（#2764 遗留项）：凭证只在
    该模块内出现，且「作废失败不阻断退出」的语义在那里统一实现。
    """
    auth_header = request.headers.get('Authorization', '')
    user_token = ''
    if auth_header.lower().startswith('bearer '):
        user_token = auth_header[7:].strip()

    if user_token:
        supabase_admin.revoke_session(user_token)

    return {'success': True, 'message': '已退出登录'}

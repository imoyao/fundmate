# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/1
# File : views.py
# 认证模块 API（退出登录统一入口）

import os

import requests
from apiflask import APIBlueprint
from flask import abort, g, request
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func

from app.domains.families.models import Family
from app.domains.users.models import ROLE_LABELS, User

auth_bp = APIBlueprint('auth', __name__, url_prefix='/api/auth')


class ResolveRequest(BaseModel):
    identifier: str


@auth_bp.post('/resolve')
def resolve_identifier():
    """登录标识解析（D10）：把"邮箱 或 用户名"收敛为规范邮箱，供前端二次登录。

    Supabase Auth 原生仅支持 "邮箱/手机号 + 密码" 登录，不支持用户名登录。
    这里作为解析层：前端拿到用户输入（可能是邮箱或用户名）后，先调用本接口，
    由本地 `users` 表把标识解析为规范 email，再交给 `signInWithPassword`。

    解析优先级：
    1. 若输入形如邮箱（含 `@`），先按 `email` 精确匹配；
    2. 否则按 `username`（不区分大小写）匹配；
    3. 仍无匹配 → 404，表示该标识不存在（不泄露任何邮箱信息）。

    本接口免登录（PUBLIC_EXACT），因为登录前必须能调用它。
    """
    from app.core.database import get_db  # 延迟导入，与测试 monkeypatch 对齐
    from app.core.validation import parse_body

    data = parse_body(ResolveRequest)
    identifier = data.identifier.strip()
    if not identifier:
        abort(400, description='登录标识不能为空')

    is_email = '@' in identifier
    with get_db() as db:
        if is_email:
            user = db.query(User).filter(User.email == identifier).order_by(User.id.asc()).first()
        else:
            user = (
                db.query(User).filter(func.lower(User.username) == identifier.lower()).order_by(User.id.asc()).first()
            )
        if user is None:
            abort(404, description='未找到该邮箱或用户名，请检查后重试')
        return {'data': {'email': user.email}, 'message': 'ok'}


@auth_bp.get('/me')
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


@auth_bp.post('/logout')
def logout():
    """退出登录。

    前端退出时统一调用本接口，并把当前 Supabase 的 access_token 通过
    Authorization 头带上来。若后端配置了 SUPABASE_URL 与
    SUPABASE_SERVICE_ROLE_KEY，则调用 Supabase Admin API 在**服务端**作废
    该会话（避免前端直接暴露认证请求、也保证 token 真正失效）；否则仅返回
    成功，由前端清理本地 token 完成退出。

    这样无论是否接入 Supabase 管理服务，退出链路都统一收敛到后端入口。
    """
    supabase_url = os.getenv('SUPABASE_URL')
    service_role_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

    auth_header = request.headers.get('Authorization', '')
    user_token = ''
    if auth_header.lower().startswith('bearer '):
        user_token = auth_header[7:].strip()

    if supabase_url and service_role_key and user_token:
        try:
            # 服务端作废指定会话，使用 service_role key（仅后端持有，不暴露给前端）
            resp = requests.post(
                f'{supabase_url.rstrip("/")}/auth/v1/logout',
                headers={
                    'apikey': service_role_key,
                    'Authorization': f'Bearer {service_role_key}',
                    'Content-Type': 'application/json',
                },
                json={'access_token': user_token},
                timeout=10,
            )
            if resp.status_code >= 400:
                logger.warning(
                    'Supabase 服务端登出返回非预期状态码 {}: {}',
                    resp.status_code,
                    resp.text,
                )
        except Exception as e:  # noqa: BLE001
            # 服务端作废失败不影响前端退出流程
            logger.warning('调用 Supabase 服务端登出失败: {}', e)
    else:
        logger.debug('未配置 Supabase 服务端凭证，跳过服务端会话作废')

    return {'success': True, 'message': '已退出登录'}
